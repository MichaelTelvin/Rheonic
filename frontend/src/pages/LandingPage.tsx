import { Activity, Gauge, ShieldCheck, Workflow, Wrench, Layers, Signal, DatabaseZap } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { PublicLayout } from "../components/PublicLayout";
import { Seo } from "../components/Seo";

export function LandingPage(): JSX.Element {
  const rootRef = useRef<HTMLElement | null>(null);
  const flowVariant: "equal" | "large-rheonic" = "equal";

  useEffect(() => {
    if (!rootRef.current || typeof IntersectionObserver === "undefined") {
      return undefined;
    }

    const targets = rootRef.current.querySelectorAll(".reveal-on-scroll");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
          }
        });
      },
      { threshold: 0.18, rootMargin: "0px 0px -8% 0px" },
    );

    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, []);

  return (
    <PublicLayout
      navAuthHref="/login"
      navAuthLabel="Sign in"
      shellClassName="public-shell--marketing"
      showDocsLink={false}
      showBetaBadge
    >
      <Seo
        title="Rheonic | Observability & Control for AI Systems"
        description="Rheonic helps teams monitor model traffic, detect anomalies, and enforce preflight guardrails before expensive provider calls are sent."
        path="/"
        jsonLd={{
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          name: "Rheonic",
          applicationCategory: "DeveloperApplication",
          operatingSystem: "Web",
          description:
            "Monitor model behavior per provider, detect anomalies, and enforce preflight guardrails for agent traffic.",
          url: window.location.origin,
        }}
      />
      <section className="landing-marketing landing" ref={rootRef}>
        <section className="landing-hero reveal-on-scroll">
          <div className="landing-hero-copy">
            <h1>Control your agent traffic before it controls your bill.</h1>
            <p>
              Monitor model behavior per provider, detect anomalies early, and enforce preflight guardrails before
              expensive calls are sent.
            </p>
            <small className="landing-hero-beta">Beta: actively testing. Expect changes.</small>
            <div className="landing-hero-cta">
              <Link className="landing-link-button modal-primary" to="/login">
                Start beta testing
              </Link>
              <Link className="landing-link-button" to="/quickstart">
                View quickstart
              </Link>
            </div>
          </div>

          <div className="landing-hero-visual">
            <div className="landing-dashboard-mock" aria-label="Mocked Rheonic dashboard preview">
              <div className="landing-mock-topbar">
                <span />
                <span />
                <span />
              </div>
              <div className="landing-mock-content">
                <div className="landing-mock-head">
                  <div>
                    <p className="landing-mock-title">LLM Control Center</p>
                    <p className="landing-mock-sub">Real-time monitoring and protection</p>
                  </div>
                  <article className="landing-mock-status">
                    <p className="landing-mock-status-line">
                      <span>API:</span>
                      <strong>Connected</strong>
                    </p>
                  </article>
                </div>

                <div className="landing-mock-filter">
                  <span>Provider</span>
                  <button type="button">Anthropic</button>
                </div>

                <div className="landing-mock-kpi-grid">
                  <article className="landing-mock-kpi">
                    <h4>Requests (60s)</h4>
                    <strong>42</strong>
                    <p>Last 60 seconds</p>
                    <div className="landing-graph-track req">
                      <span className="landing-graph-line req" />
                    </div>
                  </article>
                  <article className="landing-mock-kpi">
                    <h4>Tokens (60s)</h4>
                    <strong>128,400</strong>
                    <p>Last 60 seconds</p>
                    <div className="landing-graph-track tok">
                      <span className="landing-graph-line tok" />
                    </div>
                  </article>
                </div>

                <div className="landing-mock-bottom-grid">
                  <article className="landing-mock-list-card">
                    <h4>Incidents</h4>
                    <p><span>Near cap</span><strong>0</strong></p>
                    <p><span>Retry storm</span><strong>0</strong></p>
                    <p><span>Loop suspect</span><strong>0</strong></p>
                    <p><span>Token explosion</span><strong>0</strong></p>
                    <p><span>Cap breach</span><strong>1</strong></p>
                  </article>
                  <article className="landing-mock-list-card">
                    <h4>Preflight decisions (60m)</h4>
                    <p><span>Allowed</span><strong>2</strong></p>
                    <p><span>Warned</span><strong>0</strong></p>
                    <p><span>Blocked</span><strong>1</strong></p>
                  </article>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-section reveal-on-scroll">
          <h2>Agentic systems don’t fail quietly</h2>
          <div className="landing-pain-grid">
            <article className="landing-pain-timeline">
              <p className="landing-pain-kicker">Failure sequence</p>
              <div className="landing-pain-track">
                <article className="landing-pain-step reveal-on-scroll">
                  <div className="landing-pain-step-copy">
                    <p className="landing-pain-time">T+00:20</p>
                    <h3>Spike</h3>
                    <p>Traffic jumps without warning.</p>
                  </div>
                  <span className="landing-pain-chip">+320% req/min</span>
                </article>
                <article className="landing-pain-step reveal-on-scroll">
                  <div className="landing-pain-step-copy">
                    <p className="landing-pain-time">T+00:45</p>
                    <h3>Retry storm</h3>
                    <p>Transient errors multiply into load.</p>
                  </div>
                  <span className="landing-pain-chip">15 retries</span>
                </article>
                <article className="landing-pain-step reveal-on-scroll">
                  <div className="landing-pain-step-copy">
                    <p className="landing-pain-time">T+01:10</p>
                    <h3>Loop runaway</h3>
                    <p>One bug keeps calling until it hurts.</p>
                  </div>
                  <span className="landing-pain-chip">1,200 calls</span>
                </article>
                <article className="landing-pain-step reveal-on-scroll">
                  <div className="landing-pain-step-copy">
                    <p className="landing-pain-time">T+01:40</p>
                    <h3>Budget drain</h3>
                    <p>Minutes later, the bill is real.</p>
                  </div>
                  <span className="landing-pain-chip">$ / cap breach</span>
                </article>
              </div>
            </article>

            <article className="landing-pain-compare">
              <div className="landing-pain-compare-block">
                <p className="landing-pain-compare-label">Without a control layer</p>
                <h3>Logs</h3>
                <p>You see it after the damage.</p>
                <p>Incidents show up when costs already landed.</p>
                <p>You can’t stop the next call.</p>
              </div>
              <div className="landing-pain-compare-block is-positive">
                <p className="landing-pain-compare-label">With Rheonic</p>
                <h3>Control layer</h3>
                <p>See anomalies in real time.</p>
                <p>Preflight decisions before expensive calls.</p>
                <p>Warn or block with cooldown when needed.</p>
              </div>

              <div className="landing-pain-mini-flow">
                <span className="landing-pain-mini-node">
                  <Workflow size={13} />
                  <em>Agent</em>
                </span>
                <span className="landing-pain-mini-arrow">→</span>
                <span className="landing-pain-mini-node">
                  <Wrench size={13} />
                  <em>SDK</em>
                </span>
                <span className="landing-pain-mini-arrow">→</span>
                <span className="landing-pain-mini-node is-core">
                  <Signal size={13} />
                  <em>Rheonic</em>
                </span>
                <span className="landing-pain-mini-arrow">→</span>
                <span className="landing-pain-mini-node">
                  <DatabaseZap size={13} />
                  <em>Provider</em>
                </span>
              </div>
            </article>
          </div>
        </section>

        <section className="landing-section reveal-on-scroll">
          <h2>A control layer between your agents and model providers</h2>
          <div className="landing-capabilities">
            <article className="landing-cap-card">
              <div className="landing-cap-head">
                <span className="landing-icon-circle telemetry">
                  <Gauge size={16} />
                </span>
                <h3>Per-provider telemetry</h3>
              </div>
              <p>Real-time request and token rates per provider and project—so you see drift immediately.</p>
            </article>
            <article className="landing-cap-card">
              <div className="landing-cap-head">
                <span className="landing-icon-circle anomaly">
                  <Activity size={16} />
                </span>
                <h3>Incident detection</h3>
              </div>
              <p>Automatic incidents for near-cap, retry storms, loop suspects, and token explosions—before they cascade.</p>
            </article>
            <article className="landing-cap-card">
              <div className="landing-cap-head">
                <span className="landing-icon-circle enforcement">
                  <ShieldCheck size={16} />
                </span>
                <h3>Preflight enforcement</h3>
              </div>
              <p>Apply allow / warn / block decisions before provider calls, with cooldown to stop repeat bursts.</p>
            </article>
          </div>
        </section>

        <section className="landing-section reveal-on-scroll">
          <h2>Visual flow</h2>
          <div className={`landing-flow landing-flow--${flowVariant}`}>
            <div className="landing-flow-grid">
              <article className="landing-flow-node landing-flow-node-basic">
                <div className="landing-flow-node-content">
                  <span className="landing-flow-node-icon">
                    <Workflow size={14} />
                  </span>
                  <p className="landing-flow-node-label">Agent</p>
                </div>
              </article>
              <span className="landing-flow-link link-1" aria-hidden />
              <article className="landing-flow-node landing-flow-node-basic">
                <div className="landing-flow-node-content">
                  <span className="landing-flow-node-icon">
                    <Wrench size={14} />
                  </span>
                  <p className="landing-flow-node-label">SDK</p>
                </div>
              </article>
              <span className="landing-flow-link link-2 is-core" aria-hidden />
              <article className="landing-flow-node landing-flow-node-rheonic">
                <div className="landing-flow-rheonic-shell">
                  <h3 className="landing-flow-rheonic-head">
                    <span className="landing-flow-node-icon">
                      <Signal size={14} />
                    </span>
                    <span>Rheonic</span>
                  </h3>
                  <div className="landing-flow-rheonic-modes" aria-label="Rheonic modes">
                    <span className="is-active">Observe</span>
                    <span className="is-protect">Protect</span>
                  </div>
                </div>
              </article>
              <span className="landing-flow-link link-3 is-core" aria-hidden />
              <article className="landing-flow-node landing-flow-node-basic">
                <div className="landing-flow-node-content">
                  <span className="landing-flow-node-icon">
                    <DatabaseZap size={14} />
                  </span>
                  <p className="landing-flow-node-label">Provider</p>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section className="landing-section reveal-on-scroll">
          <h2>Why it works in practice</h2>
          <div className="landing-engineer-grid">
            <article className="landing-engineer-card">
              <Layers size={16} />
              <h3>No backend refactor</h3>
              <p>
                Drop in the SDK and start in observe mode.
                <br />
                No architectural rewrite required.
              </p>
            </article>
            <article className="landing-engineer-card">
              <DatabaseZap size={16} />
              <h3>Provider-scoped controls</h3>
              <p>
                Independent monitoring and enforcement
                <br />
                per provider.
              </p>
            </article>
            <article className="landing-engineer-card">
              <Workflow size={16} />
              <h3>SDK-first integration</h3>
              <p>
                Typed client workflows for runtime
                <br />
                telemetry and protection.
              </p>
            </article>
            <article className="landing-engineer-card">
              <Activity size={16} />
              <h3>Real signals</h3>
              <p>
                Detect loop patterns and cost acceleration
                <br />
                before incidents.
              </p>
            </article>
          </div>
        </section>

        <section className="landing-final-cta reveal-on-scroll">
          <h2>Add guardrails before your next agent experiment</h2>
          <Link className="landing-link-button modal-primary" to="/login">
            Start beta testing
          </Link>
        </section>
      </section>
    </PublicLayout>
  );
}
