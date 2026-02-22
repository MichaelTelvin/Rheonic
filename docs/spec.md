# LLMTokenBurnGuard — Specification (v1)

## 0) API conventions
- REST JSON
- Auth:
  - User auth: JWT session for web app
  - SDK ingest: `Authorization: Bearer <project_ingest_key>`

## 1) Event ingest

### POST /v1/events
Headers:
- Authorization: Bearer <project_ingest_key>

Body (Event):
```json
{
  "ts": "2026-02-12T10:22:31.123Z",
  "provider": "openai|anthropic|gemini",
  "model": "string",
  "environment": "prod|staging|dev",
  "request": {
    "endpoint": "/chat",
    "feature": "support_chat",
    "tenant_id": "tenant_123",
    "user_id": "user_456",
    "job_id": "job_789",
    "trace_id": "trace_abc",
    "prompt_hash": "sha256:...",
    "input_tokens": 1234,
    "max_output_tokens": 512
  },
  "response": {
    "output_tokens": 456,
    "total_tokens": 1690,
    "latency_ms": 842,
    "status": "ok|error",
    "error_type": "timeout|rate_limit|provider_5xx|client_error|unknown",
    "http_status": 200
  },
  "cost": {
    "currency": "USD",
    "input_cost_usd": 0.0123,
    "output_cost_usd": 0.0456,
    "total_cost_usd": 0.0579,
    "pricing_version": "2026-02-01",
    "source": "estimate|authoritative|null"
  },
  "guard": {
    "mode": "observe|protect",
    "action": "none|downgrade_model|cap_output_tokens|rate_limit|cooldown_block|serve_cache",
    "reason_code": "NONE|BURN_RATE_SPIKE|RETRY_STORM|LOOP_SUSPECT|TOKEN_EXPLOSION|BUDGET_EXCEEDED|RATE_LIMIT_LOCAL|COOLDOWN_ACTIVE",
    "policy_version": "v1",
    "decision_ms": 2
  },
  "meta": {
    "sdk_language": "python|node",
    "sdk_version": "0.1.0"
  }
}
```
Response:
	•	202 Accepted

Notes:
	•	Default: prompt_hash is stored, not raw content.
	•	Strict mode: allow prompt_hash null.



## 2) Realtime metrics

### GET /v1/metrics/realtime?project_id=…

Returns:
```
{
  "ts": "2026-02-12T10:22:40Z",
  "burn_estimated_usd_per_min": 1.32,
  "burn_authoritative_usd_per_min": 1.28,
  "burn_estimated_usd_per_hour": 56.4,
  "burn_authoritative_usd_per_hour": 55.1,
  "requests_per_min": 88,
  "retry_rate_60s": 0.14,
  "token_rate_60s": 12000,
  "top_endpoints": [{"endpoint":"/chat","burn_usd_per_min":0.72}],
  "top_tenants": [{"tenant_id":"tenant_123","burn_usd_per_min":0.58}],
  "open_incidents": 2
}
```
### GET /v1/metrics/rollup?project_id=…&from=…&to=…&interval=1m|5m|1h&group_by=endpoint|feature|tenant|model|provider

Returns:
	•	time series buckets + grouped sums



## 3) Incidents

### GET /v1/incidents?project_id=…&status=open|closed
```
Incident shape:
{
  "incident_id": "inc_123",
  "type": "RETRY_STORM|LOOP_SUSPECT|BURN_RATE_SPIKE|TOKEN_EXPLOSION",
  "status": "open|closed",
  "severity": "low|med|high|critical",
  "first_seen": "2026-02-12T10:10:00Z",
  "last_seen": "2026-02-12T10:22:40Z",
  "scope": {
    "endpoint": "/chat",
    "feature": "support_chat",
    "tenant_id": "tenant_123"
  },
  "evidence": {
    "burn_now": 1.32,
    "burn_baseline": 0.41,
    "retry_rate_60s": 0.46,
    "attempt_rate_60s": 120,
    "repeated_job_id_count": 90
  },
  "reason_code": "RETRY_STORM",
  "recommended_actions": [
    "Enable Protect cooldown 30s for endpoint=/chat",
    "Cap output tokens to 256",
    "Set max retries to 3 (app-level)"
  ]
}    
```

### POST /v1/incidents/{incident_id}/close

Closes incident.


## 4) Policy (Protect mode)


### GET /v1/policy/config?project_id=…

Returns policy config used by SDK locally.

Policy config (v1):

```
{
  "policy_version": "v1",
  "enabled": true,
  "mode": "protect",
  "budgets": {
    "monthly_usd": 200.0,
    "daily_usd": 30.0
  },
  "actions": {
    "downgrade": {
      "enabled": true,
      "fallback_chain": {
        "openai": {
          "gpt-4o": "gpt-4o-mini"
        },
        "anthropic": {
          "claude-3-5-sonnet": "claude-3-5-haiku"
        },
        "gemini": {
          "gemini-1.5-pro": "gemini-1.5-flash"
        }
      }
    },
    "cap_output_tokens": {
      "enabled": true,
      "default_max_output_tokens": 256
    },
    "rate_limit": {
      "enabled": true,
      "project_rpm": 120,
      "tenant_rpm": 30,
      "behavior": "cooldown_block",
      "cooldown_seconds": 30
    },
    "cooldown": {
      "enabled": true,
      "seconds": 30
    },
    "cache_fallback": {
      "enabled": true,
      "ttl_seconds": 120
    }
  },
  "detectors": {
    "retry_storm": {
      "retry_rate_threshold": 0.35,
      "attempt_rate_multiplier": 2.0,
      "window_seconds": 60
    },
    "burn_spike": {
      "multiplier": 3.0,
      "window_seconds": 300
    },
    "loop": {
      "job_id_repeats": 50,
      "window_seconds": 120
    },
    "token_explosion": {
      "multiplier": 3.0,
      "window_seconds": 300
    }
  }
}
```

Protect action semantics (SDK side)
	•	downgrade_model: swap request.model before sending
	•	cap_output_tokens: set max output tokens param
	•	rate_limit:
	•	local sliding window counters
	•	if exceeded: cooldown_block with typed error (or delay later)
	•	cooldown_block:
	•	raise/return typed cooldown error with retry_after
	•	serve_cache:
	•	return cached response if exact key hit, else proceed with downgrade/cap or cooldown


## 5) Alerts

Channels:
	•	Slack webhook (MVP)
	•	generic webhook (MVP)
	•	Teams Incoming Webhook / Power Automate


Triggers:
	•	incident opened or escalated (severity >= med)
	•	budget threshold crossed
	•	burn spike

Payload includes:
	•	incident type, scope, evidence, recommended actions, dashboard link

## 6) Pricing tables

### 6.1 Estimated pricing table (estimator only)
Server hosts a pricing table versioned by date.
SDK syncs periodically.
Events record `pricing_version` used for cost estimation.

Pricing table schema (server-side):
- provider
- model
- input_price_per_1m_tokens
- output_price_per_1m_tokens
- currency
- effective_from
- version

Notes:
- Pricing table is used for **estimated** cost only.
- Table updates are manual and infrequent (only when provider pricing changes).

### 6.2 Authoritative cost reconciliation (preferred)
Where available, we periodically pull authoritative usage/cost from provider reporting APIs and reconcile against estimates.

## 7) Architecture diagrams
- Generated diagrams live at:
  - `docs/architecture/incident_flow.svg`
  - `docs/architecture/protect_decision_flow.svg`
- Regenerate with: `make diagrams`
- Verify generated artifacts with: `make diagrams-check`
- Generation requires Graphviz (`dot`); the Make target runs it inside Docker.

Stored fields (per project, per interval):
- authoritative_cost_usd
- authoritative_source (provider_api | billing_export)
- reconciled_at

### 6.3 Pricing drift detection
If the difference between estimated and authoritative totals exceeds a threshold, create a warning incident and optionally alert.

Example drift rule:
- abs(estimated_usd - authoritative_usd) / max(authoritative_usd, 0.01) > 0.15

On drift:
- create `CONFIG_WARNING` incident with reason_code `PRICING_DRIFT`
- include evidence (estimated vs authoritative and interval)
- suggest updating pricing table and/or model mapping

### 6.4 Null cost handling
If token usage or pricing is unavailable, cost may be null.

Consequences:
- Risk detection (storms/loops/spikes) still works using requests/tokens where available.
- Dollar-based budget alerts may be suppressed until authoritative cost is available.

---

## 7) Risk Model vs Cost Model

### 7.1 Risk units (realtime)
Risk detection is based on:
- requests per minute
- retry rate
- input/output token rate (when available)
- slope/acceleration vs baseline
- repetition patterns (job_id/trace_id/prompt_hash)

Risk detection does **not** depend on dollar accuracy.

### 7.2 Cost units (estimated vs authoritative)
Two levels:
- **Estimated**: computed by SDK using pricing table (fast, best-effort).
- **Authoritative**: reconciled from provider reporting (preferred for budgets and accurate totals).

UI rules:
- Always label estimated cost as estimated.
- Prefer authoritative totals when available.
- If both exist, show both and highlight drift when meaningful.

---

## 8) Reconciliation job (worker)

A worker job runs periodically (recommended: every 5–15 minutes):

1. Fetch usage/cost from provider reporting APIs (where available).
2. Map provider account → project.
3. Store authoritative totals for the interval.
4. Compare to estimated totals (if present).
5. Emit drift warnings and/or budget alerts as configured.

Budget enforcement semantics:
- Observe mode: alert when authoritative (or estimated fallback) crosses thresholds.
- Protect mode: may trigger cooldown_block/downgrade actions based on realtime risk and/or budget signals (configurable).
