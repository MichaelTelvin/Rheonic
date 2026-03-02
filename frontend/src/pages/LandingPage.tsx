import { useEffect, useRef } from "react";
import { Activity, Gauge, ShieldCheck, Workflow, Wrench, Layers, Signal, DatabaseZap } from "lucide-react";
import { Link } from "react-router-dom";

import { PublicLayout } from "../components/PublicLayout";

export function LandingPage(): JSX.Element {
  const rootRef = useRef<HTMLElement | null>(null);

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
              <div className="landing-v2-mock-grid">
                <article>
                  <p>Requests / min</p>
                  <strong>2,148</strong>
                </article>
                <article>
                  <p>Tokens / min</p>
                  <strong>1.7M</strong>
                </article>
                <article className="landing-v2-graph-card">
                  <p>Realtime anomaly pulse</p>
                  <div className="landing-v2-graph-track">
                    <span className="landing-v2-graph-line" />
                  </div>
                </article>
                <article>
                  <p>Preflight state</p>
                  <strong>Protect: Warn</strong>
                </article>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-v2-section reveal-on-scroll">
          <h2>Agentic systems don’t fail quietly.</h2>
          <article className="landing-v2-problem-panel">
            <ul>
              <li>Traffic spikes without warning</li>
              <li>Retries multiply silently</li>
              <li>
                One bad loop can <span className="landing-v2-danger-underline">drain budget</span> in minutes
              </li>
            </ul>
            <p>Traditional logs show it too late. You need a control layer.</p>
          </article>
        </section>

        <section className="landing-v2-section reveal-on-scroll">
          <h2>A control layer between your agents and model providers.</h2>
          <div className="landing-v2-capabilities">
            <article className="landing-v2-cap-card">
              <span className="landing-v2-icon-circle telemetry">
                <Gauge size={16} />
              </span>
              <h3>Realtime per-provider telemetry</h3>
            </article>
            <article className="landing-v2-cap-card">
              <span className="landing-v2-icon-circle anomaly">
                <Activity size={16} />
              </span>
              <h3>Anomaly detection (near cap, retry storms, token explosions)</h3>
            </article>
            <article className="landing-v2-cap-card">
              <span className="landing-v2-icon-circle enforcement">
                <ShieldCheck size={16} />
              </span>
              <h3>Optional preflight enforcement (warn / block / cooldown)</h3>
            </article>
          </div>
        </section>

        <section className="landing-v2-section reveal-on-scroll">
          <h2>Visual flow</h2>
          <div className="landing-v2-flow">
            <div className="landing-v2-flow-chain">
              <div className="landing-v2-flow-node">
                <Workflow size={15} />
                <span>Agent</span>
              </div>
              <span className="landing-v2-flow-arrow" />
              <div className="landing-v2-flow-node">
                <Wrench size={15} />
                <span>SDK</span>
              </div>
              <span className="landing-v2-flow-arrow" />
              <div className="landing-v2-flow-node landing-v2-flow-node-core">
                <Signal size={15} />
                <span>Rheonic</span>
              </div>
              <span className="landing-v2-flow-arrow" />
              <div className="landing-v2-flow-node">
                <DatabaseZap size={15} />
                <span>Provider</span>
              </div>
            </div>
            <div className="landing-v2-mode-toggle">
              <article>
                <h3>Observe</h3>
                <p>Visibility</p>
              </article>
              <article className="is-active">
                <h3>Protect</h3>
                <p>Enforcement</p>
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
              <p>Drop in SDK instrumentation and start with observe mode.</p>
            </article>
            <article className="landing-v2-engineer-card">
              <DatabaseZap size={16} />
              <h3>Works per provider</h3>
              <p>Separate controls for OpenAI, Anthropic, and Google traffic.</p>
            </article>
            <article className="landing-v2-engineer-card">
              <Workflow size={16} />
              <h3>SDK-first</h3>
              <p>Typed client workflows for runtime telemetry and protect calls.</p>
            </article>
            <article className="landing-v2-engineer-card">
              <Activity size={16} />
              <h3>Real signals</h3>
              <p>Detect near-cap, retry storms, and loop patterns before escalation.</p>
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
