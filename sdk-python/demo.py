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


def _send_event(client: Any, provider: str, model: str, endpoint: str, total_tokens: int, feature: str, environment: str) -> None:
    capture_event(
        build_event(
            provider=provider,
            model=model,
            environment=environment,
            request={"endpoint": endpoint, "input_tokens": 1, "feature": feature},
            response={"output_tokens": 1, "total_tokens": total_tokens, "http_status": 200},
        )
    )


def _print_incident_summary(project_id: str, auth_token: str, provider: str) -> None:
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
    counts = {"low": 0, "medium": 0, "high": 0}
    for incident in incidents:
        severity = str(incident.get("severity", ""))
        if severity in counts:
            counts[severity] += 1
    print(
        "[OBSERVE] incidents "
        f"open={len(incidents)} low={counts['low']} medium={counts['medium']} high={counts['high']}"
    )


def main() -> None:
    _load_llmtbg_env_from_dotenv()

    ingest_key = os.getenv("LLMTBG_INGEST_KEY")
    if not ingest_key:
        print("LLMTBG_INGEST_KEY is required. Create a key in the dashboard Keys page first.")
        return

    provider = (os.getenv("LLMTBG_PROVIDER", "") or "").strip().lower()
    if not provider:
        print("LLMTBG_PROVIDER is required (openai | anthropic | google).")
        return
    if provider not in {"openai", "anthropic", "google"}:
        print(f"LLMTBG_PROVIDER is unsupported: {provider}")
        return

    model = (os.getenv("LLMTBG_MODEL", "") or "").strip()
    if not model:
        print(f"LLMTBG_MODEL is required for provider {provider}.")
        return

    environment = os.getenv("LLMTBG_ENVIRONMENT") or os.getenv("LLMTBG_ENV") or "dev"
    endpoint_by_provider = {
        "openai": "/chat/completions",
        "anthropic": "/v1/messages",
        "google": "/v1beta/models/generateContent",
    }
    endpoint = endpoint_by_provider.get(provider, "/chat/completions")

    demo_case = (os.getenv("LLMTBG_DEMO_CASE") or "warmup").strip().lower()
    step_sleep_ms = int(os.getenv("LLMTBG_STEP_SLEEP_MS", "800"))
    baseline_events = int(os.getenv("LLMTBG_BASELINE_EVENTS", "8"))
    baseline_tokens = int(os.getenv("LLMTBG_BASELINE_TOKENS", "100"))
    spike_tokens = int(os.getenv("LLMTBG_SPIKE_TOKENS", "60000"))
    escalation_hits = int(os.getenv("LLMTBG_ESCALATION_HITS", "3"))

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
        print("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider")

        def run_warmup() -> None:
            print("\n[STEP] Warm-up baseline behavior")
            print("[EXPECT] tiny early traffic should not create ratio-based incident")
            _send_event(client, provider, model, endpoint, 42, "demo-warmup-1", environment)
            time.sleep(step_sleep_ms / 1000)
            _send_event(client, provider, model, endpoint, 42, "demo-warmup-2", environment)
            client.flush()

        def run_spike() -> None:
            print("\n[STEP] True spike detection")
            print("[EXPECT] baseline-ready ratio+delta or warm-up early-abs should open incident")
            for i in range(baseline_events):
                _send_event(client, provider, model, endpoint, baseline_tokens, f"demo-baseline-{i + 1}", environment)
                time.sleep(step_sleep_ms / 1000)
            _send_event(client, provider, model, endpoint, spike_tokens, "demo-spike", environment)
            client.flush()

        def run_escalation() -> None:
            print("\n[STEP] Escalation behavior")
            print("[EXPECT] repeat spike hits in escalation windows promote severity")
            for i in range(escalation_hits):
                _send_event(client, provider, model, endpoint, spike_tokens, f"demo-escalation-{i + 1}", environment)
                time.sleep(step_sleep_ms / 1000)
            client.flush()

        def run_lifecycle() -> None:
            print("\n[STEP] Incident lifecycle")
            print("[EXPECT] open -> update/escalate -> resolve (manual or auto-close)")
            _send_event(client, provider, model, endpoint, spike_tokens, "demo-lifecycle-open", environment)
            time.sleep(step_sleep_ms / 1000)
            _send_event(client, provider, model, endpoint, spike_tokens, "demo-lifecycle-update", environment)
            client.flush()
            if auth_token and project_id:
                _print_incident_summary(project_id, auth_token, provider)
                print("[OBSERVE] for manual resolve, use Dashboard Incidents page or call /api/v1/incidents/{id}/resolve")
                print("[OBSERVE] auto-resolve happens after incident_auto_close_seconds inactivity")
            else:
                print("[OBSERVE] set LLMTBG_AUTH_TOKEN + LLMTBG_PROJECT_ID to print incident summary from API")

        if demo_case == "all":
            run_warmup()
            run_spike()
            run_escalation()
            run_lifecycle()
        elif demo_case == "warmup":
            run_warmup()
        elif demo_case == "spike":
            run_spike()
        elif demo_case == "escalation":
            run_escalation()
        elif demo_case == "lifecycle":
            run_lifecycle()
        else:
            print(f"Unsupported LLMTBG_DEMO_CASE: {demo_case}")
            return

        print("\n[DONE] observe demo complete")
        print(client.stats())
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
