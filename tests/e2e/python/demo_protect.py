from __future__ import annotations

import json as json_lib
import os
import sys
import time
from math import ceil
from pathlib import Path
from typing import Any

import httpx

try:
    from dashboard_session import DashboardSession
    from rheonic.client import Client
    from rheonic.protect_engine import RHEONICBlockedError
    from rheonic.providers.anthropic_adapter import instrument_anthropic
    from rheonic.providers.google_adapter import instrument_google
    from rheonic.providers.openai_adapter import instrument_openai
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    sdk_src = repo_root / "sdk-python" / "src"
    tests_src = repo_root / "tests" / "e2e" / "python"
    if str(sdk_src) not in sys.path:
        sys.path.insert(0, str(sdk_src))
    if str(tests_src) not in sys.path:
        sys.path.insert(0, str(tests_src))
    from dashboard_session import DashboardSession
    from rheonic.client import Client
    from rheonic.protect_engine import RHEONICBlockedError
    from rheonic.providers.anthropic_adapter import instrument_anthropic
    from rheonic.providers.google_adapter import instrument_google
    from rheonic.providers.openai_adapter import instrument_openai

BACKEND_BASE_URL = os.getenv("RHEONIC_BACKEND_URL", "http://localhost:8000")
PROVIDER_STUB_URL = os.getenv("RHEONIC_PROVIDER_URL", "http://localhost:8099")
_LAST_PROVIDER_CALL: dict[str, Any] | None = None
_LOCAL_PROVIDER_CALL_COUNT = 0
_PROVIDER_STUB_AVAILABLE: bool | None = None


class LoggingHttpClient:
    def __init__(self, timeout_s: float) -> None:
        self._client = httpx.Client(timeout=timeout_s)
        self.last_decision_payload: dict[str, Any] | None = None

    def post(
        self,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> httpx.Response:
        payload = json
        if url.endswith("/api/v1/protect/decision"):
            started_at = time.perf_counter()
            print("=== PROTECT DECISION REQUEST ===")
            print(json_lib.dumps(payload, indent=2, sort_keys=True))
        try:
            response = self._client.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:
            if url.endswith("/api/v1/protect/decision"):
                print(f"=== PROTECT DECISION ERROR === {exc.__class__.__name__}: {exc}")
            raise
        if url.endswith("/api/v1/protect/decision"):
            payload: dict[str, Any]
            try:
                parsed = response.json()
                payload = parsed if isinstance(parsed, dict) else {"raw": parsed}
            except Exception:
                payload = {"status_code": response.status_code, "body": response.text}
            self.last_decision_payload = payload
            header_latency_ms = response.headers.get("X-Protect-Decision-Latency-Ms")
            round_trip_latency_ms = int((time.perf_counter() - started_at) * 1000)
            print("=== PROTECT DECISION RESPONSE ===")
            if header_latency_ms is not None:
                print(f"[LATENCY] protect_server_ms={header_latency_ms} protect_round_trip_ms={round_trip_latency_ms}")
            print(json_lib.dumps(payload, indent=2, sort_keys=True))
        return response

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        return self._client.get(url, headers=headers, params=params, timeout=timeout)

    def close(self) -> None:
        self._client.close()


def _set_provider_stub_available(value: bool) -> None:
    global _PROVIDER_STUB_AVAILABLE
    _PROVIDER_STUB_AVAILABLE = value


def _provider_stub_request(method: str, path: str, **kwargs: Any) -> httpx.Response | None:
    global _PROVIDER_STUB_AVAILABLE
    try:
        response = httpx.request(
            method,
            f"{PROVIDER_STUB_URL}{path}",
            timeout=3.0,
            **kwargs,
        )
        response.raise_for_status()
    except Exception:
        if _PROVIDER_STUB_AVAILABLE is not False:
            print(f"[PROVIDER] stub unavailable at {PROVIDER_STUB_URL}; using in-process call tracking")
        _set_provider_stub_available(False)
        return None
    _set_provider_stub_available(True)
    return response


def _provider_reset() -> None:
    global _LAST_PROVIDER_CALL, _LOCAL_PROVIDER_CALL_COUNT
    _LAST_PROVIDER_CALL = None
    _LOCAL_PROVIDER_CALL_COUNT = 0
    _provider_stub_request("POST", "/reset")


def _provider_count() -> int:
    if _PROVIDER_STUB_AVAILABLE is not False:
        response = _provider_stub_request("GET", "/count")
        if response is not None:
            payload = response.json()
            return int(payload.get("count", 0)) if isinstance(payload, dict) else 0
    return _LOCAL_PROVIDER_CALL_COUNT


def _provider_last_call() -> dict[str, Any] | None:
    return _LAST_PROVIDER_CALL.copy() if isinstance(_LAST_PROVIDER_CALL, dict) else None


def _record_provider_call(payload: dict[str, Any]) -> None:
    global _LAST_PROVIDER_CALL, _LOCAL_PROVIDER_CALL_COUNT
    _LAST_PROVIDER_CALL = payload.copy()
    _LOCAL_PROVIDER_CALL_COUNT += 1


def _notify_provider_call(payload: dict[str, Any]) -> None:
    _record_provider_call(payload)
    if _PROVIDER_STUB_AVAILABLE is not False:
        _provider_stub_request("POST", "/call", json=payload)


def _extract_used_max_tokens(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    raw = payload.get("max_tokens")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    generation_config = payload.get("generation_config")
    if isinstance(generation_config, dict):
        raw = generation_config.get("max_output_tokens")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw)
    return None


def _resolve_simulated_total_tokens(payload: dict[str, Any] | None, fallback: int = 10) -> int:
    used_max_tokens = _extract_used_max_tokens(payload)
    prompt_tokens = _estimate_prompt_tokens(payload)
    return max(
        used_max_tokens if isinstance(used_max_tokens, int) and used_max_tokens > 0 else 0,
        prompt_tokens,
        fallback,
    )


def _collect_prompt_fragments(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            parts.append(trimmed)
        return
    if isinstance(value, list):
        for item in value:
            _collect_prompt_fragments(item, parts)
        return
    if not isinstance(value, dict):
        return
    text = value.get("text")
    if isinstance(text, str):
        _collect_prompt_fragments(text, parts)
    if "content" in value:
        _collect_prompt_fragments(value.get("content"), parts)


def _estimate_prompt_tokens(payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return 0
    parts: list[str] = []
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        _collect_prompt_fragments(prompt, parts)
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict):
                _collect_prompt_fragments(message.get("content"), parts)
    text = " ".join(parts).strip()
    if not text:
        return 0
    word_estimate = len(text.split())
    char_estimate = (len(text) + 3) // 4
    return max(word_estimate, char_estimate)


def _assert_line(label: str, passed: bool) -> None:
    print(f"[ASSERT] {label}" if passed else f"[ASSERT] {label} (FAILED)")


def _assert_delivery(client: Client, *, expected_min_sent: int = 0) -> None:
    stats = client.stats()
    print(f"[DEMO] sdk delivery stats: {stats}")
    sent = int(stats.get("sent", 0))
    failed = int(stats.get("failed", 0))
    queued = int(stats.get("queued", 0))
    if sent < expected_min_sent or failed > 0 or queued > 0:
        raise RuntimeError(
            f"protect demo did not fully deliver SDK events (sent={sent}, failed={failed}, queued={queued})"
        )


def _print_config_hint() -> None:
    target_hint = (os.getenv("RHEONIC_DEMO_TARGET_HINT") or "").strip() or "protect-prod-python"
    print(f"Run: make {target_hint} RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cap_breach")
    print("Optional exact provider-call visibility: python3 tests/e2e/provider_stub.py")


def _make_openai_stub() -> Any:
    class Completions:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            _notify_provider_call(kwargs)
            usage = type(
                "Usage",
                (),
                {"total_tokens": _resolve_simulated_total_tokens(kwargs)},
            )()
            return type(
                "Response",
                (),
                {"model": kwargs.get("model"), "usage": usage},
            )()

    class Chat:
        completions = Completions()

    class OpenAIStub:
        chat = Chat()

    return OpenAIStub()


def _make_anthropic_stub() -> Any:
    class Messages:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            _notify_provider_call(kwargs)
            total_tokens = _resolve_simulated_total_tokens(kwargs)
            usage = type(
                "Usage",
                (),
                {"input_tokens": 1, "output_tokens": max(total_tokens - 1, 1)},
            )()
            return type(
                "Response",
                (),
                {"model": kwargs.get("model"), "usage": usage},
            )()

    class AnthropicStub:
        messages = Messages()

    return AnthropicStub()


def _make_google_stub() -> Any:
    class UsageMetadata:
        total_token_count = 10

    class GoogleResponse:
        usage_metadata = UsageMetadata()

    class GoogleModelStub:
        model_name = ""

        @staticmethod
        def generate_content(prompt: str | dict[str, Any]) -> Any:
            payload = prompt if isinstance(prompt, dict) else {"prompt": prompt}
            _notify_provider_call(payload)
            UsageMetadata.total_token_count = _resolve_simulated_total_tokens(payload)
            return GoogleResponse()

    return GoogleModelStub()


def _send_ingest_event(
    transport: LoggingHttpClient,
    ingest_key: str,
    provider: str,
    model: str,
    *,
    total_tokens: int,
    feature: str,
    environment: str,
    token_explosion_tokens: int | None = None,
    status: str = "ok",
    http_status: int = 200,
    error_type: str | None = None,
) -> None:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "model": model,
        "environment": environment,
        "latency_ms": 120,
        "http_status": http_status,
        **({"error_type": error_type} if error_type else {}),
        "request": {
            "endpoint": "/chat/completions",
            "feature": feature,
            "input_tokens": 1,
            **({"token_explosion_tokens": token_explosion_tokens} if isinstance(token_explosion_tokens, int) else {}),
        },
        "response": {
            "output_tokens": 1,
            "total_tokens": total_tokens,
            "latency_ms": 120,
            "http_status": http_status,
            **({"error_type": error_type} if error_type else {}),
        },
        "status": status,
    }
    response = transport.post(
        f"{BACKEND_BASE_URL}/api/v1/events",
        json=payload,
        headers={"X-Project-Ingest-Key": ingest_key},
        timeout=5.0,
    )
    response.raise_for_status()


def _list_open_incidents(
    dashboard_session: DashboardSession | None,
    project_id: str,
    provider: str,
    auth_email: str,
) -> list[dict[str, Any]]:
    if dashboard_session is None or not project_id:
        print("[INCIDENTS] skipped (missing dashboard cookie session or RHEONIC_PROJECT_ID)")
        return []
    params = {"project_id": project_id, "status": "open", "provider": provider}
    try:
        payload = dashboard_session.request("/api/v1/incidents", params=params)
        return payload if isinstance(payload, list) else []
    except httpx.HTTPError as exc:
        status_code = (
            exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None else None
        )
        if status_code in {401, 403}:
            print(
                f"[INCIDENTS] skipped ({status_code} auth error; update dashboard cookie credentials for {auth_email})"
            )
            return []
        raise


def _print_incidents(
    dashboard_session: DashboardSession | None,
    project_id: str,
    provider: str,
    auth_email: str,
) -> None:
    incidents = _list_open_incidents(dashboard_session, project_id, provider, auth_email)
    counts: dict[str, int] = {}
    near_types: list[str] = []
    for incident in incidents:
        incident_type = str(incident.get("type", "unknown"))
        counts[incident_type] = counts.get(incident_type, 0) + 1
        if incident_type == "near_cap":
            evidence = incident.get("evidence")
            if isinstance(evidence, dict):
                near_type = str(evidence.get("near_cap_type", "")).strip()
                if near_type:
                    near_types.append(near_type)
    compact = ", ".join(f"{k}={counts[k]}" for k in sorted(counts)) if counts else "none"
    if near_types:
        near_compact = ",".join(sorted(set(near_types)))
        print(f"[INCIDENTS] open={len(incidents)} types={compact} near_cap_types={near_compact}")
        return
    print(f"[INCIDENTS] open={len(incidents)} types={compact}")


def _get_project_req_cap(
    dashboard_session: DashboardSession | None,
    project_id: str,
    auth_email: str,
) -> int | None:
    if dashboard_session is None or not project_id:
        return None
    try:
        payload = dashboard_session.request(f"/api/v1/projects/{project_id}/protect")
    except httpx.HTTPError as exc:
        status_code = (
            exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None else None
        )
        if status_code in {401, 403}:
            print(
                "[PROTECT] req cap lookup skipped "
                f"({status_code} auth error; update dashboard cookie "
                f"credentials for {auth_email})"
            )
            return None
        raise
    value = payload.get("protect_max_req_per_min") if isinstance(payload, dict) else None
    return value if isinstance(value, int) and value > 0 else None


def _assert_project_is_in_protect_mode(
    dashboard_session: DashboardSession | None,
    project_id: str,
    auth_email: str,
) -> None:
    if dashboard_session is None or not project_id:
        return
    try:
        payload = dashboard_session.request(f"/api/v1/projects/{project_id}/protect")
    except httpx.HTTPError as exc:
        status_code = (
            exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None else None
        )
        if status_code in {401, 403}:
            print(
                "[PROTECT] mode check skipped "
                f"({status_code} auth error; update dashboard cookie "
                f"credentials for {auth_email})"
            )
            return
        raise
    protect_enabled = bool(payload.get("protect_enabled")) if isinstance(payload, dict) else False
    if not protect_enabled:
        raise RuntimeError(
            "Protect demo requires project mode Protect. "
            "Current project mode is Observe, so protect decision counters "
            "will stay at zero even though usage metrics still increment."
        )


def _run_provider_call(
    provider: str,
    model: str,
    max_tokens: int,
    prompt_text: str,
    openai: Any,
    anthropic: Any,
    google: Any,
) -> bool:
    blocked = False
    try:
        if provider == "anthropic":
            anthropic.messages.create(
                model=model,
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=max_tokens,
            )
        elif provider == "google":
            google.generate_content(
                {
                    "prompt": prompt_text,
                    "generation_config": {"max_output_tokens": max_tokens},
                }
            )
        else:
            openai.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=max_tokens,
            )
    except RHEONICBlockedError:
        blocked = True
    return blocked


def main() -> None:
    ingest_key = os.getenv("RHEONIC_INGEST_KEY")
    if not ingest_key:
        print("RHEONIC_INGEST_KEY is required")
        _print_config_hint()
        sys.exit(1)

    provider = (os.getenv("RHEONIC_PROVIDER", "") or "").strip().lower()
    if provider not in {"openai", "anthropic", "google"}:
        print("RHEONIC_PROVIDER is required (openai | anthropic | google)")
        _print_config_hint()
        sys.exit(1)

    model = (os.getenv("RHEONIC_MODEL", "") or "").strip()
    if not model:
        print(f"RHEONIC_MODEL is required for provider {provider}")
        _print_config_hint()
        sys.exit(1)

    scenario = (os.getenv("RHEONIC_SCENARIO") or "allow").strip().lower()
    env = (os.getenv("RHEONIC_ENVIRONMENT") or "").strip() or f"protect-{int(time.time())}"
    pause_ms = int(os.getenv("RHEONIC_STEP_SLEEP_MS", "200"))
    decision_timeout_ms = int(os.getenv("RHEONIC_PROTECT_DECISION_TIMEOUT_MS", "160"))
    project_id = os.getenv("RHEONIC_PROJECT_ID", "")
    auth_email = (os.getenv("RHEONIC_AUTH_EMAIL", "") or "").strip().lower()
    auth_password = os.getenv("RHEONIC_AUTH_PASSWORD", "")
    dashboard_session: DashboardSession | None = None
    if project_id and auth_email and auth_password:
        dashboard_session = DashboardSession(BACKEND_BASE_URL)
        try:
            dashboard_session.login(auth_email, auth_password)
            print("[INCIDENTS] dashboard cookie session ready")
        except Exception as error:
            print(f"[INCIDENTS] dashboard cookie session unavailable ({error})")
            dashboard_session = None
    _assert_project_is_in_protect_mode(dashboard_session, project_id, auth_email)

    transport = LoggingHttpClient(timeout_s=5.0)
    client = Client(
        ingest_key=ingest_key,
        base_url=BACKEND_BASE_URL,
        environment=env,
        flush_interval_s=0.25,
        http_client=transport,
    )
    client._protect_engine._decision_timeout_ms = decision_timeout_ms

    openai = _make_openai_stub()
    anthropic = _make_anthropic_stub()
    google = _make_google_stub()
    google.model_name = model

    decision_feature = "loop-fixed-signature" if scenario == "loop_suspect" else "manual-protect-demo"
    instrument_openai(openai, client=client, feature=decision_feature, environment=env)
    instrument_anthropic(
        anthropic,
        client=client,
        feature=decision_feature,
        environment=env,
    )
    instrument_google(google, client=client, feature=decision_feature, environment=env)

    try:
        _provider_reset()
        before_calls = _provider_count()

        print(f"[DEMO] provider={provider} model={model} scenario={scenario}")
        print(f"[DEMO] environment={env}")
        print(f"[DEMO] protect_decision_timeout_ms={decision_timeout_ms}")
        print(f"[DEMO] decision_feature={decision_feature}")

        max_tokens = int(os.getenv("RHEONIC_MAX_TOKENS", "128"))
        call_max_tokens = max_tokens
        prompt_text = "protect demo request"
        print(f"[DEMO] max_tokens(before call)={max_tokens}")

        if scenario == "near_cap":
            print("\n[STEP] Seed near-cap traffic then expect warn")
            seed_tokens = int(os.getenv("RHEONIC_NEAR_CAP_SEED_TOKENS", "1600"))
            _send_ingest_event(
                transport,
                ingest_key,
                provider,
                model,
                total_tokens=seed_tokens,
                feature="near-cap-seed",
                environment=env,
            )
            time.sleep(pause_ms / 1000)
        elif scenario == "cap_breach":
            print("\n[STEP] Seed cap breach then expect block")
            breach_tokens = int(os.getenv("RHEONIC_CAP_BREACH_TOKENS", "5000"))
            _send_ingest_event(
                transport,
                ingest_key,
                provider,
                model,
                total_tokens=breach_tokens,
                feature="cap-breach-seed",
                environment=env,
            )
            call_max_tokens = max(max_tokens, breach_tokens)
            print(f"[STEP] cap_breach call max_tokens={call_max_tokens}")
            time.sleep(pause_ms / 1000)
        elif scenario == "req_cap_breach":
            print("\n[STEP] Seed req cap breach then expect block")
            count = int(os.getenv("RHEONIC_REQ_CAP_BREACH_COUNT", "6"))
            req_tokens = int(os.getenv("RHEONIC_CAP_BREACH_REQ_TOKENS", "1"))
            req_cap = _get_project_req_cap(dashboard_session, project_id, auth_email)
            if isinstance(req_cap, int):
                count = max(count, req_cap + 1)
                print(
                    f"[STEP] req_cap_breach target events={count} "
                    f"req_cap={req_cap if req_cap is not None else 'unknown'}"
                )
            for i in range(count):
                _send_ingest_event(
                    transport,
                    ingest_key,
                    provider,
                    model,
                    total_tokens=req_tokens,
                    feature=f"req-cap-breach-{i + 1}",
                    environment=env,
                )
                time.sleep(pause_ms / 1000)
            print(f"[STEP] req_cap_breach ingest events sent={count} (provider_calls_delta tracks provider calls only)")
        elif scenario == "retry_storm":
            print("\n[STEP] Seed failed attempts for retry storm then expect warn")
            count = int(os.getenv("RHEONIC_RETRY_STORM_COUNT", "5"))
            for i in range(count):
                _send_ingest_event(
                    transport,
                    ingest_key,
                    provider,
                    model,
                    total_tokens=50,
                    feature=f"retry-{i + 1}",
                    environment=env,
                    status="error",
                    http_status=500,
                    error_type="provider_5xx",
                )
                time.sleep(pause_ms / 1000)
        elif scenario == "loop_suspect":
            print("\n[STEP] Seed a rapid repeated sequence for loop suspect then expect warn")
            count = int(os.getenv("RHEONIC_LOOP_COUNT", "6"))
            for _ in range(count):
                _send_ingest_event(
                    transport,
                    ingest_key,
                    provider,
                    model,
                    total_tokens=60,
                    feature="loop-fixed-signature",
                    environment=env,
                )
                time.sleep(pause_ms / 1000)
        elif scenario == "token_explosion":
            print("\n[STEP] Seed token explosion growth history then expect warn")
            peak = max(int(os.getenv("RHEONIC_TOKEN_EXPLOSION_TOKENS", "5500")), 5500)
            step_one = 1900
            step_two = max(int(ceil(peak / 1.7)), 3230)
            growth_steps = [step_one, step_two]
            for growth_value in growth_steps:
                _send_ingest_event(
                    transport,
                    ingest_key,
                    provider,
                    model,
                    total_tokens=growth_value,
                    feature="token-explosion-growth",
                    environment=env,
                    token_explosion_tokens=growth_value,
                )
                time.sleep(pause_ms / 1000)
            prompt_text = " ".join(["growth"] * peak)
            call_max_tokens = max_tokens
            print(f"[STEP] token_explosion history={growth_steps} live={peak}")
            time.sleep(pause_ms / 1000)
        elif scenario == "cooldown":
            print("\n[STEP] Seed cap breach then verify cooldown blocks repeated call")
            breach_tokens = int(os.getenv("RHEONIC_CAP_BREACH_TOKENS", "5000"))
            _send_ingest_event(
                transport,
                ingest_key,
                provider,
                model,
                total_tokens=breach_tokens,
                feature="cooldown-breach-seed",
                environment=env,
            )
            call_max_tokens = max(max_tokens, breach_tokens)
            print(f"[STEP] cooldown call max_tokens={call_max_tokens}")
            time.sleep(pause_ms / 1000)

        if scenario == "cooldown":
            first_blocked = _run_provider_call(
                provider, model, call_max_tokens, prompt_text, openai, anthropic, google
            )
            second_blocked = _run_provider_call(
                provider, model, call_max_tokens, prompt_text, openai, anthropic, google
            )
            blocked = first_blocked and second_blocked
        else:
            blocked = _run_provider_call(provider, model, call_max_tokens, prompt_text, openai, anthropic, google)
        client.flush()
        after_calls = _provider_count()
        provider_calls_delta = after_calls - before_calls
        decision_payload = transport.last_decision_payload if isinstance(transport.last_decision_payload, dict) else {}
        decision_reason = str(decision_payload.get("reason", ""))
        decision_value = str(decision_payload.get("decision", "")).lower()
        clamp = decision_payload.get("clamp")
        clamp_payload = clamp if isinstance(clamp, dict) else {}
        clamp_recommended = clamp_payload.get("recommended_max_output_tokens")
        used_max_tokens = _extract_used_max_tokens(_provider_last_call())
        clamp_applied = bool(
            isinstance(clamp_recommended, int)
            and isinstance(max_tokens, int)
            and clamp_recommended < max_tokens
            and used_max_tokens == clamp_recommended
            and provider_calls_delta >= 1
        )

        print(f"[RESULT] blocked={blocked} provider_calls_delta={provider_calls_delta}")
        if scenario == "near_cap":
            print(f"[CLAMP] recommended={clamp_recommended} applied={clamp_applied} used_max_tokens={used_max_tokens}")
        if project_id and dashboard_session is not None:
            _print_incidents(dashboard_session, project_id, provider, auth_email)
        else:
            print("[INCIDENTS] skipped (set RHEONIC_PROJECT_ID, RHEONIC_AUTH_EMAIL, and RHEONIC_AUTH_PASSWORD)")

        if scenario == "allow":
            _assert_line(
                "allow passed",
                not blocked and provider_calls_delta >= 1 and decision_value == "allow",
            )
        elif scenario == "near_cap":
            _assert_line(
                "near_cap warn triggered",
                decision_value == "warn" and decision_reason == "near_cap" and not blocked,
            )
            clamp_is_recommended = isinstance(clamp_recommended, int) and clamp_recommended > 0
            clamp_should_apply = clamp_is_recommended and isinstance(max_tokens, int) and clamp_recommended < max_tokens
            clamp_used = clamp_is_recommended and used_max_tokens == clamp_recommended and provider_calls_delta >= 1
            _assert_line("clamp suggested", clamp_is_recommended)
            if decision_payload.get("apply_clamp_enabled") is True and clamp_should_apply:
                _assert_line("clamp applied", clamp_used)
            else:
                _assert_line(
                    "clamp not applied",
                    not bool(clamp_applied) and not clamp_used,
                )
        elif scenario == "cap_breach":
            _assert_line("cap breach blocked", blocked and provider_calls_delta == 0)
        elif scenario == "req_cap_breach":
            _assert_line("req_cap breach blocked", blocked and provider_calls_delta == 0)
            _assert_line(
                "req_cap breach triggered block",
                blocked and provider_calls_delta == 0,
            )
        elif scenario == "retry_storm":
            _assert_line(
                "retry_storm warn triggered from failed attempts",
                decision_value == "warn" and decision_reason == "retry_storm" and not blocked,
            )
        elif scenario == "loop_suspect":
            _assert_line(
                "loop_suspect warn triggered from a rapid repeated sequence",
                decision_value == "warn" and decision_reason == "loop_suspect" and not blocked,
            )
        elif scenario == "token_explosion":
            _assert_line(
                "token_explosion warn triggered",
                decision_value == "warn" and decision_reason == "token_explosion" and not blocked,
            )
        elif scenario == "cooldown":
            _assert_line("cooldown active", blocked and provider_calls_delta == 0)
            _assert_line(
                "cooldown active - repeated call blocked",
                blocked and provider_calls_delta == 0,
            )

        expected_sent = 1 if provider_calls_delta >= 1 else 0
        _assert_delivery(client, expected_min_sent=expected_sent)

    finally:
        client.close()
        transport.close()
        if dashboard_session is not None:
            dashboard_session.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[DEMO] interrupted by user")
        sys.exit(130)
