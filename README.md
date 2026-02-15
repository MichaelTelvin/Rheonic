# LLMTokenBurnGuard

Runtime safety layer for LLM applications.

LLMTokenBurnGuard detects runaway usage patterns (retry storms, loops, spend spikes) 
and optionally applies guardrail policies (model downgrade, token caps, rate limiting, cooldown, cache)
across OpenAI, Anthropic, and Gemini.

---

## ✨ Core Features

### Observe Mode (default)
- Real-time burn velocity tracking
- Retry storm detection
- Loop detection
- Token explosion detection
- Incident-first dashboard
- Slack/Webhook alerts
- Per-feature / per-endpoint / per-tenant attribution

### Protect Mode (opt-in)
- Model downgrade (fallback chains)
- Output token cap
- Local rate limiting
- Cooldown soft-block
- Cached fallback responses
- Deterministic, logged decisions

---

## 🏗 Architecture

- Backend: FastAPI
- Database: PostgreSQL
- Realtime counters: Redis
- Worker: RQ/Celery
- Frontend: React + Vite + TypeScript
- SDKs: Python (v1), Node (v1.1)

---

## 🔐 Privacy

By default:
- No raw prompts stored
- Only token counts, metadata, and prompt hashes
- Strict mode available (no prompt hash)

---

## 🚀 Development

Run locally with Docker:

```
docker-compose up --build
```

See /docs for:
	•	product_design.md
	•	architecture.md
	•	spec.md
	•	scope.md

⸻

📜 License

MIT License