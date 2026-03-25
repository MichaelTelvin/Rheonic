import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dashboard_session import DashboardSession
    from rheonic import build_event, capture_event, create_client
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    sdk_src = repo_root / "sdk-python" / "src"
    tests_src = repo_root / "tests" / "e2e" / "python"
    if str(sdk_src) not in sys.path:
        sys.path.insert(0, str(sdk_src))
    if str(tests_src) not in sys.path:
        sys.path.insert(0, str(tests_src))
    from dashboard_session import DashboardSession
    from rheonic import build_event, capture_event, create_client

VERBOSE = (os.getenv("RHEONIC_VERBOSE", "") or "").lower() in {"1", "true", "yes"}


def _log(message: str) -> None:
    print(message)


def _log_verbose(message: str) -> None:
    if VERBOSE:
        print(message)


def _send_event(
    provider: str,
    model: str,
    endpoint: str,
    total_tokens: int,
    feature: str,
    environment: str,
    *,
    status: str = "ok",
    http_status: int = 200,
    error_type: str | None = None,
) -> None:
    event = build_event(
        provider=provider,
        model=model,
        environment=environment,
        request={"endpoint": endpoint, "input_tokens": 1, "feature": feature},
        response={
            "output_tokens": 1,
            "total_tokens": total_tokens,
        },
    )
    # Backend ingest reads status/http_status/error_type from top-level fields.
    event["status"] = status
    event["http_status"] = http_status
    if error_type:
        event["error_type"] = error_type
    capture_event(event)


def _print_realtime_snapshot(
    dashboard_session: DashboardSession | None,
    project_id: str,
    provider: str,
    phase: str,
) -> None:
    if not VERBOSE:
        return
    if dashboard_session is None or not project_id:
        print(
            f"[SNAPSHOT] {phase}: (snapshot skipped: no dashboard session/project id)"
        )
        return
    params = {"project_id": project_id}
    if provider and provider != "all":
        params["provider"] = provider
    try:
        payload = dashboard_session.request("/api/v1/metrics/realtime", params=params)
        if not isinstance(payload, dict):
            print(f"[SNAPSHOT] {phase}: unavailable (unexpected payload)")
            return
        print(
            f"[SNAPSHOT] {phase}: req60={payload.get('requests_60s')} "
            f"tok60={payload.get('tokens_60s')}"
        )
    except Exception as error:
        print(f"[SNAPSHOT] {phase}: unavailable ({error})")


def _print_incident_summary(
    dashboard_session: DashboardSession | None,
    project_id: str,
    provider: str,
) -> None:
    if not VERBOSE:
        return
    if dashboard_session is None or not project_id:
        print("[OBSERVE] incidents: (skipped: no dashboard session/project id)")
        return
    params = {"project_id": project_id, "status": "open"}
    if provider != "all":
        params["provider"] = provider
    try:
        payload = dashboard_session.request("/api/v1/incidents", params=params)
    except Exception as error:
        print(f"[OBSERVE] incidents summary unavailable ({error})")
        return
    incidents = payload if isinstance(payload, list) else []
    counts: dict[str, int] = {}
    for incident in incidents:
        incident_type = str(incident.get("type", "unknown"))
        counts[incident_type] = counts.get(incident_type, 0) + 1
    compact = (
        ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
        if counts
        else "none"
    )
    print(f"[OBSERVE] incidents open={len(incidents)} types={compact}")


def _parse_incident_time(incident: dict[str, Any]) -> datetime | None:
    for field in ("last_seen_at", "created_at"):
        raw_value = incident.get(field)
        if not isinstance(raw_value, str) or not raw_value:
            continue
        normalized = raw_value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            continue
    return None


def _print_recent_incident_summary(
    dashboard_session: DashboardSession | None,
    project_id: str,
    provider: str,
    *,
    phase_started_at: datetime,
) -> None:
    if not VERBOSE:
        return
    if dashboard_session is None or not project_id:
        print("[OBSERVE] recent incidents: (skipped: no dashboard session/project id)")
        return
    params = {"project_id": project_id, "status": "open"}
    if provider != "all":
        params["provider"] = provider
    try:
        payload = dashboard_session.request("/api/v1/incidents", params=params)
    except Exception as error:
        print(f"[OBSERVE] recent incidents unavailable ({error})")
        return
    incidents = payload if isinstance(payload, list) else []
    recent_incidents: list[dict[str, Any]] = []
    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        incident_time = _parse_incident_time(incident)
        if incident_time is None or incident_time < phase_started_at:
            continue
        recent_incidents.append(incident)
    counts: dict[str, int] = {}
    for incident in recent_incidents:
        incident_type = str(incident.get("type", "unknown"))
        counts[incident_type] = counts.get(incident_type, 0) + 1
    compact = (
        ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
        if counts
        else "none"
    )
    print(f"[OBSERVE] recent incidents={len(recent_incidents)} types={compact}")


def _print_phase(
    dashboard_session: DashboardSession | None,
    phase: str,
    project_id: str,
    provider: str,
    *,
    phase_started_at: datetime,
) -> None:
    _print_realtime_snapshot(dashboard_session, project_id, provider, phase)
    _print_incident_summary(dashboard_session, project_id, provider)
    _print_recent_incident_summary(
        dashboard_session,
        project_id,
        provider,
        phase_started_at=phase_started_at,
    )


def _usage() -> None:
    target_hint = (
        (os.getenv("RHEONIC_DEMO_TARGET_HINT") or "").strip()
        or "demo-prod-python"
    )
    print("Example:")
    print("  RHEONIC_PROVIDER=openai")
    print("  RHEONIC_MODEL=gpt-4o-mini")
    print(
        "  RHEONIC_DEMO_CASE=steady|near_cap|retry_storm|loop_suspect|"
        "token_explosion|cap_breach|req_cap_breach|all"
    )
    print("  RHEONIC_STEP_SLEEP_MS=200")
    print("  RHEONIC_RETRY_STORM_COUNT=6")
    print("  RHEONIC_LOOP_COUNT=7")
    print("  RHEONIC_TOKEN_EXPLOSION_TOKENS=9000")
    print("  RHEONIC_CAP_BREACH_TOKENS=4000")
    print("  RHEONIC_REQ_CAP_BREACH_COUNT=6")
    print("  RHEONIC_CAP_BREACH_REQ_TOKENS=1")
    print("  RHEONIC_NEAR_CAP_TOKENS=3200")
    print(
        "  Optional snapshot/incident summary: RHEONIC_AUTH_EMAIL, "
        "RHEONIC_AUTH_PASSWORD, RHEONIC_PROJECT_ID"
    )
    print(
        f"  Run: make {target_hint} RHEONIC_PROVIDER=google "
        "RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach"
    )


def main() -> None:
    backend_base_url = os.getenv(
        "RHEONIC_BACKEND_URL", "http://localhost:8000"
    ).rstrip("/")

    ingest_key = os.getenv("RHEONIC_INGEST_KEY")
    if not ingest_key:
        print("RHEONIC_INGEST_KEY is required. Create a key in dashboard Keys page.")
        _usage()
        return

    provider = (os.getenv("RHEONIC_PROVIDER", "") or "").strip().lower()
    if provider not in {"openai", "anthropic", "google"}:
        print("RHEONIC_PROVIDER is required (openai | anthropic | google)")
        _usage()
        return

    model = (os.getenv("RHEONIC_MODEL", "") or "").strip()
    if not model:
        print(f"RHEONIC_MODEL is required for provider {provider}")
        _usage()
        return

    environment = (os.getenv("RHEONIC_ENVIRONMENT") or "").strip() or (
        f"demo-{int(time.time())}"
    )
    endpoint_by_provider = {
        "openai": "/chat/completions",
        "anthropic": "/v1/messages",
        "google": "/v1beta/models/generateContent",
    }
    endpoint = endpoint_by_provider.get(provider, "/chat/completions")

    demo_case = (os.getenv("RHEONIC_DEMO_CASE") or "steady").strip().lower()
    step_sleep_ms = int(os.getenv("RHEONIC_STEP_SLEEP_MS", "200"))
    retry_storm_count = int(os.getenv("RHEONIC_RETRY_STORM_COUNT", "6"))
    loop_count = int(os.getenv("RHEONIC_LOOP_COUNT", "7"))
    token_explosion_tokens = int(os.getenv("RHEONIC_TOKEN_EXPLOSION_TOKENS", "9000"))
    cap_breach_tokens = int(os.getenv("RHEONIC_CAP_BREACH_TOKENS", "4000"))
    cap_breach_req_count = int(os.getenv("RHEONIC_REQ_CAP_BREACH_COUNT", "6"))
    cap_breach_req_tokens = int(os.getenv("RHEONIC_CAP_BREACH_REQ_TOKENS", "1"))
    near_cap_tokens = int(os.getenv("RHEONIC_NEAR_CAP_TOKENS", "3200"))

    project_id = os.getenv("RHEONIC_PROJECT_ID", "")
    auth_email = (os.getenv("RHEONIC_AUTH_EMAIL", "") or "").strip().lower()
    auth_password = os.getenv("RHEONIC_AUTH_PASSWORD", "")
    dashboard_session: DashboardSession | None = None
    if project_id and auth_email and auth_password:
        dashboard_session = DashboardSession(backend_base_url)
        try:
            dashboard_session.login(auth_email, auth_password)
            _log_verbose("[OBSERVE] dashboard cookie session ready")
        except Exception as error:
            _log_verbose(f"[OBSERVE] dashboard cookie session unavailable ({error})")
            dashboard_session = None

    client = None
    try:
        client = create_client(
            base_url=os.getenv("RHEONIC_BASE_URL"),
            ingest_key=ingest_key,
            environment=environment,
            debug=os.getenv("RHEONIC_DEBUG", "").lower() in {"1", "true", "yes"},
        )

        _log(
            f"[DEMO] observe {demo_case} provider={provider} "
            f"model={model} environment={environment}"
        )
        _log_verbose(
            "[DEMO] params "
            f"retry_storm_count={retry_storm_count} loop_count={loop_count} "
            f"token_explosion_tokens={token_explosion_tokens} "
            f"cap_breach_tokens={cap_breach_tokens} "
            f"cap_breach_req_count={cap_breach_req_count} "
            f"cap_breach_req_tokens={cap_breach_req_tokens} "
            f"near_cap_tokens={near_cap_tokens} "
            f"step_sleep_ms={step_sleep_ms}"
        )

        def run_steady() -> None:
            _log_verbose("\n[STEP] Steady traffic / no anomaly")
            phase_started_at = datetime.now().astimezone()
            _send_event(provider, model, endpoint, 42, "steady-1", environment)
            client.flush()
            _print_phase(
                dashboard_session,
                "steady",
                project_id,
                provider,
                phase_started_at=phase_started_at,
            )

        def run_near_cap() -> None:
            _log_verbose("\n[STEP] Near-cap logging (observe)")
            _log_verbose(
                "[STEP] Requires project token/request cap configured in "
                "Settings page."
            )
            phase_started_at = datetime.now().astimezone()
            _send_event(
                provider, model, endpoint, near_cap_tokens, "near-cap", environment
            )
            client.flush()
            _print_phase(
                dashboard_session,
                "near_cap",
                project_id,
                provider,
                phase_started_at=phase_started_at,
            )

        def run_retry_storm() -> None:
            _log_verbose("\n[STEP] Retry storm")
            phase_started_at = datetime.now().astimezone()
            for i in range(retry_storm_count):
                _send_event(
                    provider,
                    model,
                    endpoint,
                    50,
                    f"retry-{i + 1}",
                    environment,
                    status="error",
                    http_status=500,
                    error_type="provider_5xx",
                )
                time.sleep(step_sleep_ms / 1000)
            client.flush()
            _print_phase(
                dashboard_session,
                "retry_storm",
                project_id,
                provider,
                phase_started_at=phase_started_at,
            )

        def run_loop_suspect() -> None:
            _log_verbose("\n[STEP] Loop suspect")
            phase_started_at = datetime.now().astimezone()
            for i in range(loop_count):
                _send_event(
                    provider,
                    model,
                    endpoint,
                    60,
                    "loop-fixed-signature",
                    environment,
                )
                time.sleep(step_sleep_ms / 1000)
            client.flush()
            _print_phase(
                dashboard_session,
                "loop_suspect",
                project_id,
                provider,
                phase_started_at=phase_started_at,
            )

        def run_token_explosion() -> None:
            _log_verbose("\n[STEP] Token explosion")
            phase_started_at = datetime.now().astimezone()
            _send_event(
                provider,
                model,
                endpoint,
                token_explosion_tokens,
                "token-explosion",
                environment,
            )
            client.flush()
            _print_phase(
                dashboard_session,
                "token_explosion",
                project_id,
                provider,
                phase_started_at=phase_started_at,
            )

        def run_cap_breach() -> None:
            _log_verbose("\n[STEP] Cap breach logging (observe)")
            _log_verbose(
                "[STEP] Requires project caps configured in Mode page "
                "(max requests/tokens per minute)."
            )
            phase_started_at = datetime.now().astimezone()
            _send_event(
                provider,
                model,
                endpoint,
                cap_breach_tokens,
                "cap-breach",
                environment,
            )
            client.flush()
            _print_phase(
                dashboard_session,
                "cap_breach",
                project_id,
                provider,
                phase_started_at=phase_started_at,
            )

        def run_req_cap_breach() -> None:
            _log_verbose("\n[STEP] Request cap breach logging (observe)")
            _log_verbose(
                "[STEP] Requires project request cap configured in Mode page "
                "(max requests per minute)."
            )
            phase_started_at = datetime.now().astimezone()
            for i in range(cap_breach_req_count):
                _send_event(
                    provider,
                    model,
                    endpoint,
                    cap_breach_req_tokens,
                    f"req-cap-breach-{i + 1}",
                    environment,
                    status="ok",
                    http_status=200,
                )
                time.sleep(step_sleep_ms / 1000)
            client.flush()
            _print_phase(
                dashboard_session,
                "req_cap_breach",
                project_id,
                provider,
                phase_started_at=phase_started_at,
            )

        if demo_case == "all":
            run_steady()
            run_near_cap()
            run_retry_storm()
            run_loop_suspect()
            run_token_explosion()
            run_cap_breach()
            run_req_cap_breach()
        elif demo_case == "steady":
            run_steady()
        elif demo_case == "near_cap":
            run_near_cap()
        elif demo_case == "retry_storm":
            run_retry_storm()
        elif demo_case == "loop_suspect":
            run_loop_suspect()
        elif demo_case == "token_explosion":
            run_token_explosion()
        elif demo_case == "cap_breach":
            run_cap_breach()
        elif demo_case == "req_cap_breach":
            run_req_cap_breach()
        else:
            print(f"Unsupported RHEONIC_DEMO_CASE: {demo_case}")
            _usage()
            return

        _log("[DONE] observe demo complete")
        _log_verbose(str(client.stats()))
    finally:
        if client is not None:
            client.close()
        if dashboard_session is not None:
            dashboard_session.close()


if __name__ == "__main__":
    main()
