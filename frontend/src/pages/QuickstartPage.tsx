import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { CodeBlock } from "../components/CodeBlock";
import { PublicLayout } from "../components/PublicLayout";

type Runtime = "node" | "python";

export function QuickstartPage(): JSX.Element {
  const [runtime, setRuntime] = useState<Runtime>("node");

  const install = useMemo(
    () =>
      runtime === "node" ? "npm install rheonic-node" : "pip install rheonic",
    [runtime],
  );

  const ingest = useMemo(
    () =>
      runtime === "node"
        ? `import { createClient, buildEvent } from "rheonic-node";

const client = createClient({
  baseUrl: process.env.RHEONIC_BACKEND_URL,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
  protectEnabled: false,
});

await client.captureEvent(
  buildEvent({
    provider: "openai",
    model: "gpt-4o-mini",
    request: { endpoint: "/chat/completions", feature: "assistant" },
    response: { total_tokens: 64, latency_ms: 120, http_status: 200 },
  }),
);`
        : `import os
from rheonic import create_client, build_event

client = create_client(
    base_url=os.environ["RHEONIC_BACKEND_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
    protect_enabled=False,
)

client.capture_event(
    build_event(
        provider="openai",
        model="gpt-4o-mini",
        request={"endpoint": "/chat/completions", "feature": "assistant"},
        response={"total_tokens": 64, "latency_ms": 120, "http_status": 200},
    )
)`,
    [runtime],
  );

  const protect = useMemo(
    () =>
      runtime === "node"
        ? `import OpenAI from "openai";
import { createClient, instrumentOpenAI, RHEONICBlockedError } from "rheonic-node";

const burnguard = createClient({
  baseUrl: process.env.RHEONIC_BACKEND_URL,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
  protectEnabled: true,
});

const openai = instrumentOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY }), {
  client: burnguard,
  endpoint: "/chat/completions",
  feature: "assistant",
});

try {
  await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "hello" }],
    max_tokens: 256,
  });
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log("Blocked by protect preflight");
  }
}`
        : `import os
from openai import OpenAI
from rheonic import create_client, instrument_openai, RHEONICBlockedError

burnguard = create_client(
    base_url=os.environ["RHEONIC_BACKEND_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
    protect_enabled=True,
)
openai_client = instrument_openai(
    OpenAI(api_key=os.environ["OPENAI_API_KEY"]),
    client=burnguard,
    endpoint="/chat/completions",
    feature="assistant",
)

try:
    openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=256,
    )
except RHEONICBlockedError:
    print("Blocked by protect preflight")`,
    [runtime],
  );

  return (
    <PublicLayout
      navAuthHref="/login"
      navAuthLabel="Sign in"
      showHomeLink
      showQuickstartLink={false}
      showDocsLink
    >
      <section className="quickstart-page">
        <div className="quickstart-docs-layout">
          <article className="quickstart-docs-content">
            <h1>Quickstart</h1>

            <section id="problem">
              <h2>What problem it solves</h2>
              <p>
                Rheonic prevents runaway LLM spend by combining provider-scoped telemetry with optional
                preflight decisioning, so you can detect and stop anomalies before costs escalate.
              </p>
            </section>

            <section id="install">
              <h2>Install</h2>
              <div className="runtime-tabs">
                <button type="button" className={runtime === "node" ? "is-active" : ""} onClick={() => setRuntime("node")}>
                  Node
                </button>
                <button type="button" className={runtime === "python" ? "is-active" : ""} onClick={() => setRuntime("python")}>
                  Python
                </button>
              </div>
              <CodeBlock code={install} language="bash" />
            </section>

            <section id="ingest">
              <h2>Minimal ingest only</h2>
              <div className="runtime-tabs">
                <button type="button" className={runtime === "node" ? "is-active" : ""} onClick={() => setRuntime("node")}>
                  Node
                </button>
                <button type="button" className={runtime === "python" ? "is-active" : ""} onClick={() => setRuntime("python")}>
                  Python
                </button>
              </div>
              <CodeBlock code={ingest} language={runtime === "node" ? "ts" : "python"} />
            </section>

            <section id="protect">
              <h2>Minimal protect wrapper</h2>
              <div className="runtime-tabs">
                <button type="button" className={runtime === "node" ? "is-active" : ""} onClick={() => setRuntime("node")}>
                  Node
                </button>
                <button type="button" className={runtime === "python" ? "is-active" : ""} onClick={() => setRuntime("python")}>
                  Python
                </button>
              </div>
              <CodeBlock code={protect} language={runtime === "node" ? "ts" : "python"} />
            </section>

            <section id="env">
              <h2>Required env vars</h2>
              <CodeBlock
                code={`RHEONIC_INGEST_KEY=<your_project_ingest_key>
RHEONIC_BACKEND_URL=http://localhost:8000`}
                language="bash"
              />
            </section>

            <section id="next" className="quickstart-next-links">
              <h2>Next links</h2>
              <div className="quickstart-next-row">
                <Link className="landing-link-button modal-primary" to="/login">
                  Sign in
                </Link>
                <Link className="landing-link-button" to="/docs">
                  Full docs inside dashboard
                </Link>
              </div>
            </section>
          </article>

          <aside className="quickstart-toc-panel">
            <h3>On this page</h3>
            <a href="#problem">What problem it solves</a>
            <a href="#install">Install</a>
            <a href="#ingest">Minimal ingest only</a>
            <a href="#protect">Minimal protect wrapper</a>
            <a href="#env">Required env vars</a>
            <a href="#next">Next links</a>
          </aside>
        </div>
      </section>
    </PublicLayout>
  );
}
