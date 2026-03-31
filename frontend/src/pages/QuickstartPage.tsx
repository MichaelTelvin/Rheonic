import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";

import { CodeBlock } from "../components/CodeBlock";
import { PublicLayout } from "../components/PublicLayout";
import { Seo } from "../components/Seo";

type Runtime = "node" | "python";
type Provider = "openai" | "anthropic" | "google";

export function QuickstartPage(): JSX.Element {
  const [runtime, setRuntime] = useState<Runtime>("node");
  const [provider, setProvider] = useState<Provider>("openai");
  const [activeSection, setActiveSection] = useState("project");
  const sectionIds = [
    "project",
    "install",
    "env",
    "instrument",
    "verify",
    "limits",
    "protect",
    "advanced",
    "next",
  ] as const;

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") {
      return undefined;
    }

    const sections = sectionIds
      .map((id) => document.getElementById(id))
      .filter((section): section is HTMLElement => section !== null);
    if (sections.length === 0) {
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) {
          setActiveSection(visible[0].target.id);
        }
      },
      { rootMargin: "-28% 0px -58% 0px", threshold: [0.1, 0.3, 0.5, 0.7] },
    );

    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  const onTocClick = (event: MouseEvent<HTMLAnchorElement>, id: string): void => {
    event.preventDefault();
    const section = document.getElementById(id);
    if (!section) {
      return;
    }
    section.scrollIntoView({ behavior: "smooth", block: "start" });
    window.history.replaceState(null, "", `#${id}`);
  };

  const install = useMemo(
    () =>
      runtime === "node" ? "npm install @rheonic/sdk" : "pip install rheonic-sdk --pre",
    [runtime],
  );

  const selectedModel = useMemo(() => {
    if (provider === "anthropic") {
      return "claude-3-5-sonnet-latest";
    }
    if (provider === "google") {
      return "gemini-1.5-pro";
    }
    return "gpt-4o-mini";
  }, [provider]);

  const ingest = useMemo(
    () =>
      runtime === "node"
        ? `import { createClient, buildEvent } from "rheonic-node";

const client = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

await client.captureEvent(
  buildEvent({
    provider: "${provider}",
    model: "${selectedModel}",
    request: { endpoint: "${provider === "google" ? "/models/generateContent" : "/chat/completions"}", feature: "assistant", token_explosion_tokens: 64 },
    response: { total_tokens: 64, latency_ms: 120, http_status: 200 },
  }),
);`
        : `import os
from rheonic import create_client, build_event

client = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)

client.capture_event(
    build_event(
        provider="${provider}",
        model="${selectedModel}",
        request={"endpoint": "${provider === "google" ? "/models/generateContent" : "/chat/completions"}", "feature": "assistant", "token_explosion_tokens": 64},
        response={"total_tokens": 64, "latency_ms": 120, "http_status": 200},
    )
)`,
    [runtime, provider, selectedModel],
  );

  const protect = useMemo(
    () => {
      if (runtime === "node" && provider === "openai") {
        return `import OpenAI from "openai";
import { createClient, instrumentOpenAI, RHEONICBlockedError } from "rheonic-node";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const openai = instrumentOpenAI(new OpenAI({ apiKey: process.env.OPENAI_API_KEY! }), {
  client: rheonic,
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
    console.log(JSON.stringify({
      reason: error.reason,
      retry_after_seconds: error.retry_after_seconds,
      blocked_until: error.blocked_until,
      trace_id: error.trace_id,
      request_id: error.request_id,
    }, null, 2));
  }
}`;
      }
      if (runtime === "node" && provider === "anthropic") {
        return `import Anthropic from "@anthropic-ai/sdk";
import { createClient, RHEONICBlockedError } from "rheonic-node";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const anthropic = rheonic.instrumentAnthropic(new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! }));

try {
  await anthropic.messages.create({
    model: "claude-3-5-sonnet-latest",
    max_tokens: 256,
    messages: [{ role: "user", content: "hello" }],
  });
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log(JSON.stringify({
      reason: error.reason,
      retry_after_seconds: error.retry_after_seconds,
      blocked_until: error.blocked_until,
      trace_id: error.trace_id,
      request_id: error.request_id,
    }, null, 2));
  }
}`;
      }
      if (runtime === "node" && provider === "google") {
        return `import { GoogleGenerativeAI } from "@google/generative-ai";
import { createClient, RHEONICBlockedError } from "rheonic-node";

const rheonic = createClient({
  baseUrl: process.env.RHEONIC_BASE_URL!,
  ingestKey: process.env.RHEONIC_INGEST_KEY!,
});

const genAI = new GoogleGenerativeAI(process.env.GOOGLE_API_KEY!);
const model = rheonic.instrumentGoogle(genAI.getGenerativeModel({ model: "gemini-1.5-pro" }));

try {
  await model.generateContent("hello");
} catch (error) {
  if (error instanceof RHEONICBlockedError) {
    console.log(JSON.stringify({
      reason: error.reason,
      retry_after_seconds: error.retry_after_seconds,
      blocked_until: error.blocked_until,
      trace_id: error.trace_id,
      request_id: error.request_id,
    }, null, 2));
  }
}`;
      }
      if (provider === "anthropic") {
        return `import json
import os
from anthropic import Anthropic
from rheonic import create_client, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
anthropic_client = rheonic.instrument_anthropic(
    Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
)

try:
    anthropic_client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=256,
        messages=[{"role": "user", "content": "hello"}],
    )
except RHEONICBlockedError as error:
    print(json.dumps({
        "reason": error.reason,
        "retry_after_seconds": error.retry_after_seconds,
        "blocked_until": error.blocked_until,
        "trace_id": error.trace_id,
        "request_id": error.request_id,
    }, indent=2))`;
      }
      if (provider === "google") {
        return `import json
import os
import google.generativeai as genai
from rheonic import create_client, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
google_model = rheonic.instrument_google(genai.GenerativeModel("gemini-1.5-pro"))

try:
    google_model.generate_content("hello")
except RHEONICBlockedError as error:
    print(json.dumps({
        "reason": error.reason,
        "retry_after_seconds": error.retry_after_seconds,
        "blocked_until": error.blocked_until,
        "trace_id": error.trace_id,
        "request_id": error.request_id,
    }, indent=2))`;
      }
      return `import json
import os
from openai import OpenAI
from rheonic import create_client, instrument_openai, RHEONICBlockedError

rheonic = create_client(
    base_url=os.environ["RHEONIC_BASE_URL"],
    ingest_key=os.environ["RHEONIC_INGEST_KEY"],
)
openai_client = instrument_openai(
    OpenAI(api_key=os.environ["OPENAI_API_KEY"]),
    client=rheonic,
    endpoint="/chat/completions",
    feature="assistant",
)

try:
    openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=256,
    )
except RHEONICBlockedError as error:
    print(json.dumps({
        "reason": error.reason,
        "retry_after_seconds": error.retry_after_seconds,
        "blocked_until": error.blocked_until,
        "trace_id": error.trace_id,
        "request_id": error.request_id,
    }, indent=2))`;
    },
    [runtime, provider],
  );
  const stepIcon = (
    <span className="quickstart-step-icon" aria-hidden="true">
      <svg viewBox="0 0 20 20" fill="none">
        <path d="M10 4.8v9.2M6.7 10.9 10 14.6l3.3-3.7" />
      </svg>
    </span>
  );

  return (
    <PublicLayout
      navAuthHref="/login"
      navAuthLabel="Sign in"
      shellClassName="public-shell--quickstart"
      showHomeLink
      showQuickstartLink={false}
      showDocsLink
      docsLinkLabel="Docs"
      showBetaBadge
    >
      <Seo
        title="Rheonic Quickstart | Integrate OpenAI, Anthropic, and Google"
        description="Set up Rheonic in minutes with Node or Python. Instrument provider calls, capture custom events, and enable protect-mode guardrails."
        path="/quickstart"
        jsonLd={{
          "@context": "https://schema.org",
          "@type": "TechArticle",
          headline: "Rheonic Quickstart",
          description:
            "Guide for integrating Rheonic with OpenAI, Anthropic, and Google providers using Node or Python.",
          about: ["LLM observability", "LLM guardrails", "API integration"],
          mainEntityOfPage: `${window.location.origin}/quickstart`,
        }}
      />
      <section className="quickstart-page quickstart">
        <div className="quickstart-docs-layout">
          <article className="quickstart-docs-content">
            <h1>Quickstart</h1>
            <p className="quickstart-lede">
              Follow these steps to start in Observe mode, verify traffic,
              <br />
              then enable Protect once caps are configured.
            </p>

            <section id="project" className="quickstart-step-card">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Create a project</h2>
              </div>
              <p className="quickstart-step-path">Dashboard → Projects → Create project → Keys → Create key</p>
              <p>
                You&apos;ll use this key to authenticate telemetry and preflight requests.
                <br />
                Copy the backend base URL shown in your project dashboard.
              </p>
            </section>

            <section id="install" className="quickstart-step-card">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Install SDK</h2>
              </div>
              <div className="runtime-tabs quickstart-bookmark-tabs">
                <button type="button" className={runtime === "node" ? "is-active" : ""} onClick={() => setRuntime("node")}>
                  Node
                </button>
                <button type="button" className={runtime === "python" ? "is-active" : ""} onClick={() => setRuntime("python")}>
                  Python
                </button>
              </div>
              <CodeBlock code={install} language="bash" />
              <div className="quickstart-download-row" aria-label="SDK download options">
                <a
                  href="https://www.npmjs.com/package/@rheonic/sdk"
                  className={`landing-link-button${runtime === "node" ? " modal-primary" : ""}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Node package
                </a>
                <a
                  href="https://pypi.org/project/rheonic-sdk"
                  className={`landing-link-button${runtime === "python" ? " modal-primary" : ""}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Python package
                </a>
              </div>
            </section>

            <section id="env" className="quickstart-step-card">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Set environment variables</h2>
              </div>
              <CodeBlock
                code={`RHEONIC_INGEST_KEY=<your_project_ingest_key>
RHEONIC_BASE_URL=<value_shown_in_dashboard>`}
                language="bash"
              />
            </section>

            <section id="instrument" className="quickstart-step-card">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Instrument provider calls</h2>
              </div>
              <p>Wrap your provider SDK once.</p>
              <div className="quickstart-step-callout">
                <p>Telemetry is captured automatically after each provider call.</p>
                <p>Enforcement follows Project mode in the dashboard (Observe / Protect).</p>
              </div>
              <div className="runtime-tabs">
                <button type="button" className={runtime === "node" ? "is-active" : ""} onClick={() => setRuntime("node")}>
                  Node
                </button>
                <button type="button" className={runtime === "python" ? "is-active" : ""} onClick={() => setRuntime("python")}>
                  Python
                </button>
              </div>
              <div className="quickstart-code-stack quickstart-code-stack--instrument">
                <div className="runtime-tabs quickstart-provider-tabs">
                  <button type="button" className={provider === "openai" ? "is-active" : ""} onClick={() => setProvider("openai")}>
                    OpenAI
                  </button>
                  <button type="button" className={provider === "anthropic" ? "is-active" : ""} onClick={() => setProvider("anthropic")}>
                    Anthropic
                  </button>
                  <button type="button" className={provider === "google" ? "is-active" : ""} onClick={() => setProvider("google")}>
                    Google
                  </button>
                </div>
                <CodeBlock code={protect} language={runtime === "node" ? "ts" : "python"} />
              </div>
              <div className="quickstart-step-callout">
                <p>
                  On block, SDK instrumentation raises <code>RHEONICBlockedError</code> with agent-visible feedback:
                  <code>reason</code>, <code>retry_after_seconds</code>, <code>blocked_until</code>, <code>trace_id</code>,
                  and <code>request_id</code>.
                </p>
                <p>
                  The main reasons are <code>tok_cap_breach</code>, <code>req_cap_breach</code>, <code>cooldown_active</code>,
                  and <code>fail_closed</code>.
                </p>
              </div>
              <p className="quickstart-step-muted">
                Keep one long-lived SDK client per app process. Initialize it during app startup and reuse it for all
                capture and instrumentation calls so Rheonic can avoid repeated protect cold-start latency.
              </p>
            </section>

            <section id="verify" className="quickstart-step-card">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Verify in Observe mode</h2>
              </div>
              <p>Make one provider call. Open the dashboard and confirm traffic appears.</p>
              <p>
                Incidents surface detector states such as failed retry storms, rapid repeated loop sequences, and sudden
                token growth when those patterns appear.
              </p>
              <p className="quickstart-step-muted">Dashboard path: Dashboard → Metrics or Incidents</p>
            </section>

            <section id="limits" className="quickstart-step-card">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Set request and token limits</h2>
              </div>
              <p>In Project Settings, configure request and token limits per provider.</p>
              <p className="quickstart-step-muted">Dashboard path: Dashboard → Project Settings → Limits</p>
            </section>

            <section id="protect" className="quickstart-step-card">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Enable Protect mode</h2>
              </div>
              <p>Switch Project mode from Observe to Protect to activate enforcement.</p>
              <p className="quickstart-step-muted">Dashboard path: Dashboard → Project Settings → Mode</p>
            </section>

            <section id="advanced" className="quickstart-step-card quickstart-step-card--advanced">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>
                  Optional: custom event capture <span className="quickstart-advanced-pill">Advanced</span>
                </h2>
              </div>
              <p className="quickstart-step-intro-spacious">Use this only if you can&apos;t instrument a provider SDK or need custom events.</p>
              <div className="runtime-tabs">
                <button type="button" className={runtime === "node" ? "is-active" : ""} onClick={() => setRuntime("node")}>
                  Node
                </button>
                <button type="button" className={runtime === "python" ? "is-active" : ""} onClick={() => setRuntime("python")}>
                  Python
                </button>
              </div>
              <div className="quickstart-code-stack quickstart-code-stack--advanced">
                <div className="runtime-tabs quickstart-provider-tabs">
                  <button type="button" className={provider === "openai" ? "is-active" : ""} onClick={() => setProvider("openai")}>
                    OpenAI
                  </button>
                  <button type="button" className={provider === "anthropic" ? "is-active" : ""} onClick={() => setProvider("anthropic")}>
                    Anthropic
                  </button>
                  <button type="button" className={provider === "google" ? "is-active" : ""} onClick={() => setProvider("google")}>
                    Google
                  </button>
                </div>
                <CodeBlock code={ingest} language={runtime === "node" ? "ts" : "python"} />
              </div>
            </section>

            <section id="next" className="quickstart-step-card quickstart-next-links">
              <div className="quickstart-step-head">
                {stepIcon}
                <h2>Next step</h2>
              </div>
              <p className="quickstart-next-copy">
                Create a project, generate an ingest key, and run your first instrumented call.
              </p>
              <div className="quickstart-actions-row">
                <div className="quickstart-next-row">
                  <Link className="landing-link-button modal-primary" to="/login">
                    Open dashboard setup
                  </Link>
                  <Link className="landing-link-button" to="/docs">
                    Open dashboard docs
                  </Link>
                </div>
              </div>
            </section>
          </article>

          <aside className="quickstart-toc-panel">
            <h3>On this page</h3>
            <a
              href="#project"
              className={activeSection === "project" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "project")}
            >
              Create a project
            </a>
            <a
              href="#install"
              className={activeSection === "install" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "install")}
            >
              Install SDK
            </a>
            <a href="#env" className={activeSection === "env" ? "is-active" : ""} onClick={(event) => onTocClick(event, "env")}>
              Set environment variables
            </a>
            <a
              href="#instrument"
              className={activeSection === "instrument" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "instrument")}
            >
              Instrument provider calls
            </a>
            <a
              href="#verify"
              className={activeSection === "verify" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "verify")}
            >
              Verify in Observe mode
            </a>
            <a
              href="#limits"
              className={activeSection === "limits" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "limits")}
            >
              Set request and token limits
            </a>
            <a
              href="#protect"
              className={activeSection === "protect" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "protect")}
            >
              Enable Protect mode
            </a>
            <a
              href="#advanced"
              className={activeSection === "advanced" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "advanced")}
            >
              Advanced custom capture
            </a>
            <a href="#next" className={activeSection === "next" ? "is-active" : ""} onClick={(event) => onTocClick(event, "next")}>
              Next step
            </a>
          </aside>
        </div>
      </section>
    </PublicLayout>
  );
}
