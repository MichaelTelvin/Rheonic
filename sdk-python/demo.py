import os
import time
from pathlib import Path
import sys
from typing import Any

import httpx

sdk_src = Path(__file__).resolve().parent / "src"
if str(sdk_src) not in sys.path:
    sys.path.insert(0, str(sdk_src))

from llmtokenburnguard import build_event, capture_event, create_client


def _load_llmtbg_env_from_dotenv() -> None:
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("LLMTBG_"):
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


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


def _print_realtime_snapshot(project_id: str, auth_token: str, provider: str, phase: str) -> None:
    if not auth_token or not project_id:
        print(f"[SNAPSHOT] {phase}: (snapshot skipped: no auth token/project id)")
        return
    params = {"project_id": project_id}
    if provider and provider != "all":
        params["provider"] = provider
    try:
        response = httpx.get(
            "http://localhost:8000/api/v1/metrics/realtime",
            params=params,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=5.0,
        )
        if response.status_code != 200:
            print(f"[SNAPSHOT] {phase}: unavailable (status={response.status_code})")
            return
        payload = response.json()
        if not isinstance(payload, dict):
            print(f"[SNAPSHOT] {phase}: unavailable (unexpected payload)")
            return
        print(
            f"[SNAPSHOT] {phase}: req60={payload.get('requests_60s')} tok60={payload.get('tokens_60s')}"
        )
    except Exception as error:
        print(f"[SNAPSHOT] {phase}: unavailable ({error})")


def _print_incident_summary(project_id: str, auth_token: str, provider: str) -> None:
    if not auth_token or not project_id:
        print("[OBSERVE] incidents: (skipped: no auth token/project id)")
        return
    params = {"project_id": project_id, "status": "open"}
    if provider != "all":
        params["provider"] = provider
    response = httpx.get(
        "http://localhost:8000/api/v1/incidents",
        params=params,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=5.0,
    )
    if response.status_code != 200:
        print(f"[OBSERVE] incidents summary unavailable (status={response.status_code})")
        return
    incidents = response.json() if isinstance(response.json(), list) else []
    counts: dict[str, int] = {}
    for incident in incidents:
        incident_type = str(incident.get("type", "unknown"))
        counts[incident_type] = counts.get(incident_type, 0) + 1
    compact = ", ".join(f"{key}={counts[key]}" for key in sorted(counts)) if counts else "none"
    print(f"[OBSERVE] incidents open={len(incidents)} types={compact}")


def _print_phase(phase: str, project_id: str, auth_token: str, provider: str) -> None:
    _print_realtime_snapshot(project_id, auth_token, provider, phase)
    _print_incident_summary(project_id, auth_token, provider)


def _usage() -> None:
    print("Example:")
    print("  LLMTBG_PROVIDER=openai")
    print("  LLMTBG_MODEL=gpt-4o-mini")
    print("  LLMTBG_DEMO_CASE=steady|retry_storm|loop_suspect|token_explosion|cap_breach|req_cap_breach|all")
    print("  LLMTBG_STEP_SLEEP_MS=200")
    print("  LLMTBG_RETRY_STORM_COUNT=6")
    print("  LLMTBG_LOOP_COUNT=7")
    print("  LLMTBG_TOKEN_EXPLOSION_TOKENS=9000")
    print("  LLMTBG_CAP_BREACH_TOKENS=4000")
    print("  LLMTBG_CAP_BREACH_REQ_COUNT=6")
    print("  LLMTBG_CAP_BREACH_REQ_TOKENS=1")
    print("  Optional snapshot/incident summary: LLMTBG_AUTH_TOKEN, LLMTBG_PROJECT_ID")


def main() -> None:
    _load_llmtbg_env_from_dotenv()

    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required. Create a key in dashboard Keys page.")
        _usage()
        return

    provider = (os.getenv("LLMTBG_PROVIDER", "") or "").strip().lower()
    if provider not in {"openai", "anthropic", "google"}:
        print("LLMTBG_PROVIDER is required (openai | anthropic | google)")
        _usage()
        return

    model = (os.getenv("LLMTBG_MODEL", "") or "").strip()
    if not model:
        print(f"LLMTBG_MODEL is required for provider {provider}")
        _usage()
        return

    environment = (os.getenv("LLMTBG_ENVIRONMENT") or "").strip() or f"demo-{int(time.time())}"
    endpoint_by_provider = {
        "openai": "/chat/completions",
        "anthropic": "/v1/messages",
        "google": "/v1beta/models/generateContent",
    }
    endpoint = endpoint_by_provider.get(provider, "/chat/completions")

    demo_case = (os.getenv("LLMTBG_DEMO_CASE") or "steady").strip().lower()
    step_sleep_ms = int(os.getenv("LLMTBG_STEP_SLEEP_MS", "200"))
    retry_storm_count = int(os.getenv("LLMTBG_RETRY_STORM_COUNT", "6"))
    loop_count = int(os.getenv("LLMTBG_LOOP_COUNT", "7"))
    token_explosion_tokens = int(os.getenv("LLMTBG_TOKEN_EXPLOSION_TOKENS", "9000"))
    cap_breach_tokens = int(os.getenv("LLMTBG_CAP_BREACH_TOKENS", "4000"))
    cap_breach_req_count = int(os.getenv("LLMTBG_CAP_BREACH_REQ_COUNT", "6"))
    cap_breach_req_tokens = int(os.getenv("LLMTBG_CAP_BREACH_REQ_TOKENS", "1"))

    auth_token = os.getenv("LLMTBG_AUTH_TOKEN", "")
    project_id = os.getenv("LLMTBG_PROJECT_ID", "")

    client = None
    try:
        client = create_client(
            base_url=os.getenv("LLMTBG_BASE_URL"),
            ingest_key=ingest_key,
            protect_enabled=False,
            environment=environment,
            debug=os.getenv("LLMTBG_DEBUG", "").lower() in {"1", "true", "yes"},
        )

        print(f"[DEMO] provider={provider} model={model} case={demo_case}")
        print(f"[DEMO] environment={environment}")
        print(
            "[DEMO] params "
            f"retry_storm_count={retry_storm_count} loop_count={loop_count} "
            f"token_explosion_tokens={token_explosion_tokens} cap_breach_tokens={cap_breach_tokens} "
            f"cap_breach_req_count={cap_breach_req_count} cap_breach_req_tokens={cap_breach_req_tokens} "
            f"step_sleep_ms={step_sleep_ms}"
        )

        def run_steady() -> None:
            print("\n[STEP] Steady traffic / no anomaly")
            _send_event(provider, model, endpoint, 42, "steady-1", environment)
            time.sleep(step_sleep_ms / 1000)
            _send_event(provider, model, endpoint, 42, "steady-2", environment)
            client.flush()
            _print_phase("steady", project_id, auth_token, provider)

        def run_retry_storm() -> None:
            print("\n[STEP] Retry storm")
            for i in range(retry_storm_count):
                _send_event(
                    provider,
                    model,
                    endpoint,
                    50,
                    f"retry-{i+1}",
                    environment,
                    status="error",
                    http_status=500,
                    error_type="provider_5xx",
                )
                time.sleep(step_sleep_ms / 1000)
            client.flush()
            _print_phase("retry_storm", project_id, auth_token, provider)

        def run_loop_suspect() -> None:
            print("\n[STEP] Loop suspect")
            for i in range(loop_count):
                _send_event(provider, model, endpoint, 60, "loop-fixed-signature", environment)
                time.sleep(step_sleep_ms / 1000)
            client.flush()
            _print_phase("loop_suspect", project_id, auth_token, provider)

        def run_token_explosion() -> None:
            print("\n[STEP] Token explosion")
            _send_event(provider, model, endpoint, token_explosion_tokens, "token-explosion", environment)
            client.flush()
            _print_phase("token_explosion", project_id, auth_token, provider)

        def run_cap_breach() -> None:
            print("\n[STEP] Cap breach logging (observe)")
            print("[STEP] Requires project caps configured in Mode page (max requests/tokens per minute).")
            _send_event(provider, model, endpoint, cap_breach_tokens, "cap-breach", environment)
            client.flush()
            _print_phase("cap_breach", project_id, auth_token, provider)

        def run_req_cap_breach() -> None:
            print("\n[STEP] Request cap breach logging (observe)")
            print("[STEP] Requires project request cap configured in Mode page (max requests per minute).")
            for i in range(cap_breach_req_count):
                _send_event(
                    provider,
                    model,
                    endpoint,
                    cap_breach_req_tokens,
                    f"req-cap-breach-{i+1}",
                    environment,
                    status="ok",
                    http_status=200,
                )
                time.sleep(step_sleep_ms / 1000)
            client.flush()
            _print_phase("req_cap_breach", project_id, auth_token, provider)

        if demo_case == "all":
            run_steady()
            run_retry_storm()
            run_loop_suspect()
            run_token_explosion()
            run_cap_breach()
            run_req_cap_breach()
        elif demo_case == "steady":
            run_steady()
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
            print(f"Unsupported LLMTBG_DEMO_CASE: {demo_case}")
            _usage()
            return

        print("\n[DONE] observe demo complete")
        print(client.stats())
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
