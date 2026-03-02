import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";

import { CodeBlock } from "../components/CodeBlock";
import { PublicLayout } from "../components/PublicLayout";

type Runtime = "node" | "python";

export function QuickstartPage(): JSX.Element {
  const [runtime, setRuntime] = useState<Runtime>("node");
  const [activeSection, setActiveSection] = useState("problem");
  const sectionIds = ["problem", "install", "ingest", "protect", "env", "next"] as const;

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") {
      return;
    }

    const sections = sectionIds
      .map((id) => document.getElementById(id))
      .filter((section): section is HTMLElement => section !== null);
    if (sections.length === 0) {
      return;
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
      shellClassName="quickstart-v2-shell"
      showHomeLink
      showQuickstartLink={false}
      showDocsLink
    >
      <section className="quickstart-page quickstart-v2">
        <div className="quickstart-docs-layout">
          <article className="quickstart-docs-content">
            <h1>Quickstart</h1>
            <p className="quickstart-v2-lede">
              Instrument provider traffic first, then enable protect mode once thresholds are calibrated.
            </p>

            <section id="problem">
              <h2>What this gives you</h2>
              <p>
                Rheonic adds a control layer between agent calls and model providers so runaway traffic is visible and
                enforceable before spend spikes.
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
              <h2>Capture telemetry</h2>
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
              <h2>Enable protect wrapper</h2>
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
              <h2>Next step</h2>
              <p className="quickstart-v2-next-copy">Verify events are flowing in observe mode, then move to protect mode.</p>
              <div className="quickstart-next-row">
                <Link className="landing-link-button modal-primary" to="/login">
                  Start testing
                </Link>
                <Link className="landing-link-button" to="/docs">
                  Open dashboard docs
                </Link>
              </div>
            </section>
          </article>

          <aside className="quickstart-toc-panel">
            <h3>On this page</h3>
            <a
              href="#problem"
              className={activeSection === "problem" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "problem")}
            >
              What this gives you
            </a>
            <a
              href="#install"
              className={activeSection === "install" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "install")}
            >
              Install
            </a>
            <a
              href="#ingest"
              className={activeSection === "ingest" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "ingest")}
            >
              Capture telemetry
            </a>
            <a
              href="#protect"
              className={activeSection === "protect" ? "is-active" : ""}
              onClick={(event) => onTocClick(event, "protect")}
            >
              Enable protect wrapper
            </a>
            <a href="#env" className={activeSection === "env" ? "is-active" : ""} onClick={(event) => onTocClick(event, "env")}>
              Required env vars
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
