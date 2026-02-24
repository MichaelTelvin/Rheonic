# LLMTokenBurnGuard — Product Design (v1)

## 1) One-liner
A runtime safety layer for LLM applications that detects runaway usage patterns (loops, retry storms, spend spikes) and optionally applies guardrail policies (downgrade, cap, rate-limit, cooldown, cache) across OpenAI, Anthropic, and Google models — with minimal integration and an incident-first dashboard.

## 2) Problem
LLM apps fail in production in predictable, expensive ways:
- **Infinite loops / agents stuck** → repeated API calls for hours.
- **Retry storms** (429/5xx/timeouts) → exponential retries multiply spend.
- **Sudden spend spikes** after deploys or traffic bursts.
- **One tenant/feature** drains budget or destroys MRR margins.

Vendor dashboards and general observability tools help *see spend*, but commonly fail to:
- attribute spend to *business context* (feature/endpoint/tenant/job),
- detect runaway patterns early and explain why,
- provide practical, safe guardrail actions inside the app layer.

## 3) Target users (ICP)
Primary:
- Indie AI SaaS founders and small teams shipping AI features fast
- AI agencies building LLM features for clients
- Startups without mature FinOps/observability infra

Secondary (later):
- Larger teams needing cross-provider, multi-project, per-tenant guardrails

## 4) Competitive landscape (positioning)
What exists:
- Vendor dashboards (usage/cost)
- Monitoring/observability vendors (Grafana/Datadog integrations)
- Cost monitoring products (e.g., proxy + tracking + alerts)
- OSS “budget breaker” libraries (e.g., stop after budget is hit)

Our posture:
- We do **not** win by building “another cost dashboard”.
- We win by being the **runaway detection + safety policy engine**:
  - incident-first UI,
  - business-context attribution,
  - optional protect actions,
  - no proxy required.

## 5) Product pillars
### Pillar A — Incident-first observability (Observe Mode)
Observe Mode is not “accounting tables”.
It is “production safety radar”:
- detect runaway patterns
- classify “why” (reason codes)
- show scope (feature/endpoint/tenant/job)
- suggest fixes (actionable)

### Pillar B — Optional runtime protection (Protect Mode)
Protect Mode is explicit opt-in. It provides safe, deterministic actions:
- downgrade model (fallback chain)
- cap output tokens
- local rate limiting (soft protection)
- cooldown soft-block with typed error
- serve cached fallback if available
- retry-storm mitigation guidance (do not amplify storms)

### Pillar C — Minimal integration, no prompt rewriting
- Integration must take <10 minutes.
- SDK wraps provider calls and emits events asynchronously.
- We **do not rewrite prompts** or modify content by default.

## 6) Core concepts
### Modes
**Observe Mode (default)**
- Collect per-call events + tags
- Real-time burn velocity & anomaly detection
- Incidents feed + alerts
- No behavior changes to customer traffic

**Protect Mode (opt-in)**
- Everything in Observe Mode
- Plus policy evaluation and safe actions
- Decisions are logged and explainable

### “Runaway” patterns (v1)
- **RETRY_STORM**: elevated retry rate AND elevated attempts/min
- **LOOP_SUSPECT**: repeated job_id/trace_id or repeated prompt_hash pattern
- **BURN_RATE_SPIKE**: spend velocity jumps above baseline
- **TOKEN_EXPLOSION**: input/output tokens spike vs baseline for endpoint/feature

## 7) UX summary
### Observe Mode dashboard (default landing after login)
- “What is on fire right now?” (Incidents list)
- Live risk indicators:
  - burn/min and slope
  - retry density
  - top risky endpoints/tenants
- Incident drilldown:
  - evidence metrics
  - timeline
  - recommended actions

### Protect Mode settings
- Toggle enable
- Configure budgets and rate limits
- Configure provider fallback chains
- Configure output caps
- Configure cooldown policy
- Enable cache fallback (TTL, scope)

## 8) Privacy & data handling
Default: store no raw prompts.
- Store only:
  - token counts, latency, status/error
  - tags (feature/endpoint/tenant/job)
  - prompt hash (optional, default ON but configurable)
- Offer “strict mode”:
  - no prompt hash, only lengths

## 9) Monetization (initial)
- Trial (time-limited)
- Subscription tiers by:
  - monthly events volume
  - number of projects
  - Protect Mode availability + advanced policies
- Upsell path:
  - Observe → “we detected storms/spikes” → Protect

## 10) Non-goals (explicit)
- No prompt rewriting/“remove please”
- Not a general APM replacement
- Not a proxy-required product
- Not a full agent framework
