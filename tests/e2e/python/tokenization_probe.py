from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

sdk_src = Path(__file__).resolve().parents[3] / "sdk-python" / "src"
if str(sdk_src) not in sys.path:
    sys.path.insert(0, str(sdk_src))

from rheonic.token_estimator import estimate_input_tokens  # noqa: E402


def _build_payload(model: str, text: str) -> dict[str, object]:
    provider = os.getenv("RHEONIC_PROVIDER", "openai").strip().lower()
    if provider == "anthropic":
        return {
            "model": model,
            "messages": [{"role": "user", "content": text}],
        }
    if provider == "google":
        return {
            "model": model,
            "prompt": text,
        }
    return {
        "model": model,
        "messages": [{"role": "user", "content": text}],
    }


def _make_text(length: int) -> str:
    seed = "protect demo request "
    repeated = (seed * ((length // len(seed)) + 2))[:length]
    return repeated


def _measure_once(payload: dict[str, object]) -> tuple[int | None, float]:
    started_at = time.perf_counter()
    value = estimate_input_tokens(payload)
    latency_ms = (time.perf_counter() - started_at) * 1000
    return value, latency_ms


def _measure_repeated(payload: dict[str, object], iterations: int) -> tuple[int | None, list[float]]:
    values: list[int | None] = []
    latencies: list[float] = []
    for _ in range(iterations):
        value, latency_ms = _measure_once(payload)
        values.append(value)
        latencies.append(latency_ms)
    first = values[0] if values else None
    return first, latencies


def _summary(latencies: list[float]) -> str:
    return (
        f"avg={statistics.mean(latencies):.3f}ms "
        f"min={min(latencies):.3f}ms "
        f"max={max(latencies):.3f}ms "
        f"p50={statistics.median(latencies):.3f}ms"
    )


def main() -> None:
    model = os.getenv("RHEONIC_MODEL", "gpt-4o-mini").strip()
    if not model:
        raise SystemExit("RHEONIC_MODEL is required")

    sizes = [16, 64, 256, 1024, 4096]
    extra = os.getenv("RHEONIC_PROBE_TEXT_SIZES", "").strip()
    if extra:
        sizes = [int(part.strip()) for part in extra.split(",") if part.strip()]

    iterations = int(os.getenv("RHEONIC_TOKEN_PROBE_ITERATIONS", "20"))

    print(f"model={model}")
    print(f"iterations={iterations}")
    print(f"sizes={sizes}")

    for size in sizes:
        text = _make_text(size)
        payload = _build_payload(model, text)

        first_value, first_latency_ms = _measure_once(payload)
        second_value, second_latency_ms = _measure_once(payload)
        repeated_value, repeated_latencies = _measure_repeated(payload, iterations)

        print(f"\nsize={size}")
        print(
            f"first tokens={first_value} first_ms={first_latency_ms:.3f} "
            f"second tokens={second_value} second_ms={second_latency_ms:.3f}"
        )
        print(
            f"repeated tokens={repeated_value} "
            f"{_summary(repeated_latencies)}"
        )


if __name__ == "__main__":
    main()
