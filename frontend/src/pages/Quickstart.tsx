import { useState } from "react";
import { Link } from "react-router-dom";

import { PublicLayout } from "../components/PublicLayout";

function CopyableCodeBlock({ code, language }: { code: string; language: string }): JSX.Element {
  const [copied, setCopied] = useState<boolean>(false);

  const copyCode = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="quickstart-code">
      <button type="button" className="quickstart-copy-btn" onClick={() => void copyCode()}>
        {copied ? "Copied" : "Copy"}
      </button>
      <pre>
        <code className={`language-${language}`}>{code}</code>
      </pre>
    </div>
  );
}

export function Quickstart(): JSX.Element {
  const nodeIngest = `import { createClient, buildEvent } from "rheonic-node";

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
);`;

  const pyIngest = `import os
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
)`;

  const nodeProtect = `import OpenAI from "openai";
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
}`;

  const pyProtect = `import os
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
    print("Blocked by protect preflight")`;

  return (
    <PublicLayout
      navAuthHref="/login"
      navAuthLabel="Login / Create account"
      shellClassName="quickstart-shell"
      showHomeLink
      showQuickstartLink={false}
    >
      <section>
        <div className="quickstart-layout">
          <article className="quickstart-content">
            <h1>Quickstart</h1>

            <section id="problem">
              <h2>What problem it solves</h2>
              <p>
                Rheonic helps teams prevent runaway LLM spend and unstable traffic by combining provider-aware
                telemetry with preflight protect decisions. You can monitor request/token rates in real time, open
                incidents on anomalies, and enforce caps before costly calls are sent to providers.
              </p>
            </section>

            <section id="install">
              <h2>Install</h2>
              <p>Node SDK</p>
              <CopyableCodeBlock code={`npm install rheonic-node`} language="bash" />
              <p>Python SDK</p>
              <CopyableCodeBlock code={`pip install rheonic`} language="bash" />
            </section>

            <section id="ingest">
              <h2>Minimal ingest only</h2>
              <p>Node / TypeScript</p>
              <CopyableCodeBlock code={nodeIngest} language="ts" />
              <p>Python</p>
              <CopyableCodeBlock code={pyIngest} language="python" />
            </section>

            <section id="protect">
              <h2>Minimal protect wrapper</h2>
              <p>Node / TypeScript</p>
              <CopyableCodeBlock code={nodeProtect} language="ts" />
              <p>Python</p>
              <CopyableCodeBlock code={pyProtect} language="python" />
            </section>

            <section id="env">
              <h2>Required env vars</h2>
              <CopyableCodeBlock
                code={`RHEONIC_BACKEND_URL=http://localhost:8000
RHEONIC_INGEST_KEY=<your_ingest_key>`}
                language="bash"
              />
            </section>

            <section id="links" className="quickstart-links">
              <Link className="landing-link-button modal-primary" to="/login">
                Create account / Login
              </Link>
              <Link className="landing-link-button" to="/app/docs">
                Full docs inside dashboard
              </Link>
            </section>
          </article>

          <aside className="quickstart-toc" aria-label="Table of contents">
            <h2>On this page</h2>
            <a href="#problem">What problem it solves</a>
            <a href="#install">Install</a>
            <a href="#ingest">Minimal ingest only</a>
            <a href="#protect">Minimal protect wrapper</a>
            <a href="#env">Required env vars</a>
            <a href="#links">Next links</a>
          </aside>
        </div>
      </section>
    </PublicLayout>
  );
}
