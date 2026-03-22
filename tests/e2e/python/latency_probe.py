from __future__ import annotations

import math
import os
import statistics
import time
from dataclasses import dataclass

import httpx


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    return value


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass
class ProbeResult:
    round_trip_ms: float
    server_ms: float | None
    status_code: int
    http_version: str
    via: str | None
    server: str | None
    alt_svc: str | None


def _probe_once(
    client: httpx.Client,
    base_url: str,
    ingest_key: str,
    provider: str,
    model: str,
    environment: str,
    max_output_tokens: int,
    feature: str,
) -> ProbeResult:
    started_at = time.perf_counter()
    response = client.post(
        f"{base_url.rstrip('/')}/api/v1/protect/decision",
        json={
            "provider": provider,
            "model": model,
            "environment": environment,
            "feature": feature,
            "input_tokens_estimate": 3,
            "max_output_tokens": max_output_tokens,
        },
        headers={
            "Content-Type": "application/json",
            "X-Project-Ingest-Key": ingest_key,
        },
    )
    round_trip_ms = (time.perf_counter() - started_at) * 1000
    header_server_ms = response.headers.get("X-Protect-Decision-Latency-Ms")
    return ProbeResult(
        round_trip_ms=round_trip_ms,
        server_ms=float(header_server_ms) if header_server_ms is not None else None,
        status_code=response.status_code,
        http_version=response.http_version,
        via=response.headers.get("Via"),
        server=response.headers.get("Server"),
        alt_svc=response.headers.get("Alt-Svc"),
    )


def _run_mode(
    label: str,
    base_url: str,
    ingest_key: str,
    provider: str,
    model: str,
    environment: str,
    max_output_tokens: int,
    feature: str,
    iterations: int,
    timeout_s: float,
    reuse_client: bool,
) -> None:
    print(f"\n=== {label} ===")
    print(f"base_url={base_url}")
    print(f"reuse_client={reuse_client} iterations={iterations}")

    results: list[ProbeResult] = []
    shared_client = httpx.Client(timeout=timeout_s) if reuse_client else None

    try:
        for idx in range(iterations):
            client = shared_client or httpx.Client(timeout=timeout_s)
            try:
                result = _probe_once(
                    client=client,
                    base_url=base_url,
                    ingest_key=ingest_key,
                    provider=provider,
                    model=model,
                    environment=environment,
                    max_output_tokens=max_output_tokens,
                    feature=feature,
                )
                results.append(result)
                print(
                    f"#{idx + 1} status={result.status_code} http={result.http_version} "
                    f"server_ms={result.server_ms} round_trip_ms={result.round_trip_ms:.1f}"
                )
                if idx == 0:
                    print(f"headers: server={result.server!r} via={result.via!r} alt_svc={result.alt_svc!r}")
            finally:
                if not reuse_client:
                    client.close()
    finally:
        if shared_client is not None:
            shared_client.close()

    round_trips = [item.round_trip_ms for item in results]
    server_samples = [item.server_ms for item in results if item.server_ms is not None]
    print(
        "summary:"
        f" round_trip_avg={statistics.mean(round_trips):.1f}ms"
        f" p50={_quantile(round_trips, 0.50):.1f}ms"
        f" p95={_quantile(round_trips, 0.95):.1f}ms"
    )
    if server_samples:
        print(
            "server:"
            f" avg={statistics.mean(server_samples):.1f}ms"
            f" p50={_quantile(server_samples, 0.50):.1f}ms"
            f" p95={_quantile(server_samples, 0.95):.1f}ms"
        )


def main() -> None:
    ingest_key = _env("RHEONIC_INGEST_KEY")
    if not ingest_key:
        raise SystemExit("RHEONIC_INGEST_KEY is required")

    base_url = _env("RHEONIC_BACKEND_URL", "http://localhost:8000")
    direct_base_url = _env("RHEONIC_DIRECT_BACKEND_URL")
    provider = _env("RHEONIC_PROVIDER", "openai")
    model = _env("RHEONIC_MODEL", "gpt-4o-mini")
    environment = _env("RHEONIC_ENVIRONMENT", "latency-probe")
    feature = _env("RHEONIC_PROBE_FEATURE", "latency-probe")
    iterations = int(_env("RHEONIC_PROBE_ITERATIONS", "8"))
    timeout_s = float(_env("RHEONIC_PROBE_TIMEOUT_S", "5"))
    max_output_tokens = int(_env("RHEONIC_MAX_TOKENS", "128"))

    _run_mode(
        label="proxied-shared-client",
        base_url=base_url,
        ingest_key=ingest_key,
        provider=provider,
        model=model,
        environment=environment,
        max_output_tokens=max_output_tokens,
        feature=feature,
        iterations=iterations,
        timeout_s=timeout_s,
        reuse_client=True,
    )
    _run_mode(
        label="proxied-fresh-client",
        base_url=base_url,
        ingest_key=ingest_key,
        provider=provider,
        model=model,
        environment=environment,
        max_output_tokens=max_output_tokens,
        feature=feature,
        iterations=iterations,
        timeout_s=timeout_s,
        reuse_client=False,
    )

    if direct_base_url:
        _run_mode(
            label="direct-shared-client",
            base_url=direct_base_url,
            ingest_key=ingest_key,
            provider=provider,
            model=model,
            environment=environment,
            max_output_tokens=max_output_tokens,
            feature=feature,
            iterations=iterations,
            timeout_s=timeout_s,
            reuse_client=True,
        )
        _run_mode(
            label="direct-fresh-client",
            base_url=direct_base_url,
            ingest_key=ingest_key,
            provider=provider,
            model=model,
            environment=environment,
            max_output_tokens=max_output_tokens,
            feature=feature,
            iterations=iterations,
            timeout_s=timeout_s,
            reuse_client=False,
        )


if __name__ == "__main__":
    main()
