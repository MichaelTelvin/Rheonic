import { useEffect, useRef } from "react";
import { Activity, Gauge, ShieldCheck, Workflow, Wrench, Layers, Signal, DatabaseZap } from "lucide-react";
import { Link } from "react-router-dom";

import { PublicLayout } from "../components/PublicLayout";

export function LandingPage(): JSX.Element {
  const rootRef = useRef<HTMLElement | null>(null);
  const flowVariant: "equal" | "large-rheonic" = "equal";

  useEffect(() => {
    if (!rootRef.current || typeof IntersectionObserver === "undefined") {
      return;
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
      shellClassName="public-shell-marketing"
      showDocsLink={false}
    >
      <section className="landing-marketing landing-v2" ref={rootRef}>
        <section className="landing-v2-hero reveal-on-scroll">
          <div className="landing-v2-hero-copy">
            <h1>Control your agent traffic before it controls your bill.</h1>
            <p>
              Monitor model behavior per provider, detect anomalies early, and enforce preflight guardrails before
              expensive calls are sent.
            </p>
            <div className="landing-v2-hero-cta">
              <Link className="landing-link-button modal-primary" to="/login">
                Start testing
              </Link>
              <Link className="landing-link-button" to="/quickstart">
                View quickstart
              </Link>
            </div>
          </div>

          <div className="landing-v2-hero-visual">
            <div className="landing-v2-dashboard-mock" aria-label="Mocked Rheonic dashboard preview">
              <div className="landing-v2-mock-topbar">
                <span />
                <span />
                <span />
              </div>
              <div className="landing-v2-mock-content">
                <div className="landing-v2-mock-head">
                  <div>
                    <p className="landing-v2-mock-title">LLM Control Center</p>
                    <p className="landing-v2-mock-sub">Real-time monitoring and protection</p>
                  </div>
                  <article className="landing-v2-mock-status">
                    <p className="landing-v2-mock-status-line">
                      <span>API:</span>
                      <strong>Connected</strong>
                    </p>
                  </article>
                </div>

                <div className="landing-v2-mock-filter">
                  <span>Provider</span>
                  <button type="button">Anthropic</button>
                </div>

                <div className="landing-v2-mock-kpi-grid">
                  <article className="landing-v2-mock-kpi">
                    <h4>Requests (60s)</h4>
                    <strong>42</strong>
                    <p>Last 60 seconds</p>
                    <div className="landing-v2-graph-track req">
                      <span className="landing-v2-graph-line req" />
                    </div>
                  </article>
                  <article className="landing-v2-mock-kpi">
                    <h4>Tokens (60s)</h4>
                    <strong>128,400</strong>
                    <p>Last 60 seconds</p>
                    <div className="landing-v2-graph-track tok">
                      <span className="landing-v2-graph-line tok" />
                    </div>
                  </article>
                </div>

                <div className="landing-v2-mock-bottom-grid">
                  <article className="landing-v2-mock-list-card">
                    <h4>Incidents</h4>
                    <p><span>Near cap</span><strong>0</strong></p>
                    <p><span>Retry storm</span><strong>0</strong></p>
                    <p><span>Loop suspect</span><strong>0</strong></p>
                    <p><span>Token explosion</span><strong>0</strong></p>
                    <p><span>Cap breach</span><strong>1</strong></p>
                  </article>
                  <article className="landing-v2-mock-list-card">
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

        <section className="landing-v2-section reveal-on-scroll">
          <h2>Agentic systems don’t fail quietly.</h2>
          <div className="landing-v2-pain-grid">
            <article className="landing-v2-pain-timeline">
              <p className="landing-v2-pain-kicker">Failure sequence</p>
              <div className="landing-v2-pain-track">
                <article className="landing-v2-pain-step reveal-on-scroll">
                  <div className="landing-v2-pain-step-copy">
                    <p className="landing-v2-pain-time">T+00:20</p>
                    <h3>Spike</h3>
                    <p>Traffic jumps without warning.</p>
                  </div>
                  <span className="landing-v2-pain-chip">+320% req/min</span>
                </article>
                <article className="landing-v2-pain-step reveal-on-scroll">
                  <div className="landing-v2-pain-step-copy">
                    <p className="landing-v2-pain-time">T+00:45</p>
                    <h3>Retry storm</h3>
                    <p>Transient errors multiply into load.</p>
                  </div>
                  <span className="landing-v2-pain-chip">15 retries</span>
                </article>
                <article className="landing-v2-pain-step reveal-on-scroll">
                  <div className="landing-v2-pain-step-copy">
                    <p className="landing-v2-pain-time">T+01:10</p>
                    <h3>Loop runaway</h3>
                    <p>One bug keeps calling until it hurts.</p>
                  </div>
                  <span className="landing-v2-pain-chip">1,200 calls</span>
                </article>
                <article className="landing-v2-pain-step reveal-on-scroll">
                  <div className="landing-v2-pain-step-copy">
                    <p className="landing-v2-pain-time">T+01:40</p>
                    <h3>Budget drain</h3>
                    <p>Minutes later, the bill is real.</p>
                  </div>
                  <span className="landing-v2-pain-chip">$ / cap breach</span>
                </article>
              </div>
            </article>

            <article className="landing-v2-pain-compare">
              <div className="landing-v2-pain-compare-block">
                <p className="landing-v2-pain-compare-label">Without a control layer</p>
                <h3>Logs</h3>
                <p>You see it after the damage.</p>
                <p>Incidents show up when costs already landed.</p>
                <p>You can’t stop the next call.</p>
              </div>
              <div className="landing-v2-pain-compare-block is-positive">
                <p className="landing-v2-pain-compare-label">With Rheonic</p>
                <h3>Control layer</h3>
                <p>See anomalies in real time.</p>
                <p>Preflight decisions before expensive calls.</p>
                <p>Warn or block with cooldown when needed.</p>
              </div>

              <div className="landing-v2-pain-mini-flow">
                <span className="landing-v2-pain-mini-node">
                  <Workflow size={13} />
                  <em>Agent</em>
                </span>
                <span className="landing-v2-pain-mini-arrow">→</span>
                <span className="landing-v2-pain-mini-node">
                  <Wrench size={13} />
                  <em>SDK</em>
                </span>
                <span className="landing-v2-pain-mini-arrow">→</span>
                <span className="landing-v2-pain-mini-node is-core">
                  <Signal size={13} />
                  <em>Rheonic</em>
                </span>
                <span className="landing-v2-pain-mini-arrow">→</span>
                <span className="landing-v2-pain-mini-node">
                  <DatabaseZap size={13} />
                  <em>Provider</em>
                </span>
              </div>
            </article>
          </div>
        </section>

        <section className="landing-v2-section reveal-on-scroll">
          <h2>A control layer between your agents and model providers.</h2>
          <div className="landing-v2-capabilities">
            <article className="landing-v2-cap-card">
              <div className="landing-v2-cap-head">
                <span className="landing-v2-icon-circle telemetry">
                  <Gauge size={16} />
                </span>
                <h3>Per-provider telemetry</h3>
              </div>
              <p>Real-time request and token rates per provider and project—so you see drift immediately.</p>
            </article>
            <article className="landing-v2-cap-card">
              <div className="landing-v2-cap-head">
                <span className="landing-v2-icon-circle anomaly">
                  <Activity size={16} />
                </span>
                <h3>Incident detection</h3>
              </div>
              <p>Automatic incidents for near-cap, retry storms, loop suspects, and token explosions—before they cascade.</p>
            </article>
            <article className="landing-v2-cap-card">
              <div className="landing-v2-cap-head">
                <span className="landing-v2-icon-circle enforcement">
                  <ShieldCheck size={16} />
                </span>
                <h3>Preflight enforcement</h3>
              </div>
              <p>Apply allow / warn / block decisions before provider calls, with cooldown to stop repeat bursts.</p>
            </article>
          </div>
        </section>

        <section className="landing-v2-section reveal-on-scroll">
          <h2>Visual flow</h2>
          <div className={`landing-v2-flow landing-v2-flow--${flowVariant}`}>
            <div className="landing-v2-flow-grid">
              <article className="landing-v2-flow-node landing-v2-flow-node-basic">
                <div className="landing-v2-flow-node-content">
                  <span className="landing-v2-flow-node-icon">
                    <Workflow size={14} />
                  </span>
                  <p className="landing-v2-flow-node-label">Agent</p>
                </div>
              </article>
              <span className="landing-v2-flow-link" aria-hidden />
              <article className="landing-v2-flow-node landing-v2-flow-node-basic">
                <div className="landing-v2-flow-node-content">
                  <span className="landing-v2-flow-node-icon">
                    <Wrench size={14} />
                  </span>
                  <p className="landing-v2-flow-node-label">SDK</p>
                </div>
              </article>
              <span className="landing-v2-flow-link" aria-hidden />
              <article className="landing-v2-flow-node landing-v2-flow-node-rheonic">
                <div className="landing-v2-flow-rheonic-shell">
                  <h3 className="landing-v2-flow-rheonic-head">
                    <span className="landing-v2-flow-node-icon">
                      <Signal size={14} />
                    </span>
                    <span>Rheonic</span>
                  </h3>
                  <div className="landing-v2-flow-rheonic-modes" aria-label="Rheonic modes">
                    <span>Observe</span>
                    <span>Protect</span>
                  </div>
                </div>
              </article>
              <span className="landing-v2-flow-link" aria-hidden />
              <article className="landing-v2-flow-node landing-v2-flow-node-basic">
                <div className="landing-v2-flow-node-content">
                  <span className="landing-v2-flow-node-icon">
                    <DatabaseZap size={14} />
                  </span>
                  <p className="landing-v2-flow-node-label">Provider</p>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section className="landing-v2-section reveal-on-scroll">
          <h2>Why it works in practice</h2>
          <div className="landing-v2-engineer-grid">
            <article className="landing-v2-engineer-card">
              <Layers size={16} />
              <h3>No backend refactor</h3>
              <p>Drop in the SDK and start in observe mode. No architectural rewrite required.</p>
            </article>
            <article className="landing-v2-engineer-card">
              <DatabaseZap size={16} />
              <h3>Provider-scoped controls</h3>
              <p>Independent monitoring and enforcement across OpenAI, Anthropic, and Google.</p>
            </article>
            <article className="landing-v2-engineer-card">
              <Workflow size={16} />
              <h3>SDK-first integration</h3>
              <p>Typed client workflows built for runtime telemetry and protection.</p>
            </article>
            <article className="landing-v2-engineer-card">
              <Activity size={16} />
              <h3>Real signals</h3>
              <p>Detect loop patterns and cost acceleration before they become incidents.</p>
            </article>
          </div>
        </section>

        <section className="landing-v2-final-cta reveal-on-scroll">
          <h2>Add guardrails before your next agent experiment.</h2>
          <Link className="landing-link-button modal-primary" to="/login">
            Start testing
          </Link>
        </section>
      </section>
    </PublicLayout>
  );
}
