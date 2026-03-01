import { Link } from "react-router-dom";
import { motion } from "framer-motion";

import { PublicLayout } from "../components/PublicLayout";

const reveal = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
};

export function Landing(): JSX.Element {
  return (
    <PublicLayout
      navAuthHref="/login"
      navAuthLabel="Login / Create account"
      shellClassName="landing-shell"
    >
      <section aria-label="Landing">
        <motion.section
          className="marketing-hero"
          initial="hidden"
          animate="visible"
          variants={reveal}
          transition={{ duration: 0.45, ease: "easeOut" }}
        >
          <motion.div className="marketing-hero-copy" variants={reveal} transition={{ duration: 0.45, delay: 0.05 }}>
            <h1>Guardrails and visibility for runaway token burn</h1>
            <p>
              Track per-provider token/request rates and prevent overspend with preflight caps, warnings, and
              webhooks.
            </p>
            <div className="marketing-hero-actions">
              <Link className="landing-link-button modal-primary" to="/login">
                Create account / Login
              </Link>
              <Link className="landing-link-button" to="/quickstart">
                Quickstart
              </Link>
            </div>
          </motion.div>
          <motion.div
            className="marketing-hero-visual"
            aria-hidden="true"
            variants={reveal}
            transition={{ duration: 0.45, delay: 0.12 }}
          >
            <div className="mock-browser">
              <div className="mock-browser-header">
                <span />
                <span />
                <span />
              </div>
              <div className="mock-browser-body">
                <div className="mock-kpi-row">
                  <div className="mock-kpi-card">
                    <p>Requests (60s)</p>
                    <strong>72</strong>
                  </div>
                  <div className="mock-kpi-card">
                    <p>Tokens (60s)</p>
                    <strong>18.4k</strong>
                  </div>
                </div>
                <div className="mock-kpi-row">
                  <div className="mock-kpi-card">
                    <p>Open incidents</p>
                    <strong>3</strong>
                  </div>
                  <div className="mock-kpi-card">
                    <p>Decisions (60m)</p>
                    <strong>133</strong>
                  </div>
                </div>
                <div className="mock-decisions">
                  <p>Protect decisions</p>
                  <div><span>Allowed</span><strong>124</strong></div>
                  <div><span>Warned</span><strong>7</strong></div>
                  <div><span>Blocked</span><strong>2</strong></div>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.section>

        <motion.section
          className="marketing-chip-row"
          aria-label="Value chips"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.25 }}
          variants={reveal}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          <p className="marketing-chip">Works per provider: OpenAI / Anthropic / Google</p>
          <p className="marketing-chip">Real-time counters + incidents</p>
          <p className="marketing-chip">Protect mode blocks cap breaches</p>
          <p className="marketing-chip">Webhook dispatch for operational alerts</p>
        </motion.section>

        <motion.section
          className="marketing-section marketing-problem-solution"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.25 }}
          variants={reveal}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          <article className="marketing-problem-card">
            <h2>Why it exists</h2>
            <p>
              Unchecked LLM traffic can spike unexpectedly, turning one hot path into runaway costs and unstable
              behavior across providers.
            </p>
          </article>
          <article className="marketing-problem-card">
            <h2>What you get</h2>
            <p>
              A provider-scoped control center that surfaces anomalies early and enforces preflight guardrails before
              expensive calls are sent.
            </p>
          </article>
        </motion.section>

        <motion.section
          className="marketing-section"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.25 }}
          variants={reveal}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          <h2>Core capabilities</h2>
          <div className="marketing-feature-grid">
            <motion.article className="marketing-feature-card" whileHover={{ y: -2 }}>
              <p className="marketing-feature-icon">R</p>
              <h3>Real-time per-provider counters</h3>
              <p>Monitor request and token velocity by project and provider in one dashboard.</p>
            </motion.article>
            <motion.article className="marketing-feature-card" whileHover={{ y: -2 }}>
              <p className="marketing-feature-icon">I</p>
              <h3>Incident coverage</h3>
              <p>Track near_cap, cap_breach, retry_storm, loop_suspect, and token_explosion incidents.</p>
            </motion.article>
            <motion.article className="marketing-feature-card" whileHover={{ y: -2 }}>
              <p className="marketing-feature-icon">P</p>
              <h3>Protect mode preflight</h3>
              <p>Apply allow/warn/block decisions with cooldown to stop overspend before provider calls.</p>
            </motion.article>
            <motion.article className="marketing-feature-card" whileHover={{ y: -2 }}>
              <p className="marketing-feature-icon">W</p>
              <h3>Webhook automation</h3>
              <p>Dispatch protect-mode webhooks for actionable alerts and operational workflows.</p>
            </motion.article>
            <motion.article className="marketing-feature-card" whileHover={{ y: -2 }}>
              <p className="marketing-feature-icon">C</p>
              <h3>Cooldown control</h3>
              <p>Avoid repeated bursts after hard blocks by respecting block cooldown windows.</p>
            </motion.article>
            <motion.article className="marketing-feature-card" whileHover={{ y: -2 }}>
              <p className="marketing-feature-icon">S</p>
              <h3>SDK wrappers</h3>
              <p>Instrument OpenAI, Anthropic, and Google provider calls without changing backend routes.</p>
            </motion.article>
          </div>
        </motion.section>

        <motion.section
          className="marketing-section"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.25 }}
          variants={reveal}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          <h2>How it works</h2>
          <div className="marketing-step-grid">
            <article className="marketing-step-card">
              <span className="marketing-step-icon">1</span>
              <h3>Install SDK</h3>
              <p>Add Node or Python SDK with your ingest key and backend URL.</p>
            </article>
            <article className="marketing-step-card">
              <span className="marketing-step-icon">2</span>
              <h3>Capture events</h3>
              <p>Send provider events to track request and token velocity in real time.</p>
            </article>
            <article className="marketing-step-card">
              <span className="marketing-step-icon">3</span>
              <h3>Enable Protect</h3>
              <p>Turn on preflight allow/warn/block decisions and webhook dispatch.</p>
            </article>
          </div>
        </motion.section>

        <motion.section
          className="marketing-section"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.25 }}
          variants={reveal}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          <h2>Protect vs Observe</h2>
          <div className="marketing-compare">
            <article className="marketing-compare-card">
              <h3>Observe</h3>
              <p>Capture telemetry and incidents for visibility without enforcement.</p>
            </article>
            <article className="marketing-compare-card">
              <h3>Protect</h3>
              <p>Evaluate preflight decisions to warn/block and trigger webhook workflows.</p>
            </article>
          </div>
        </motion.section>

        <motion.section
          className="marketing-cta"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.4 }}
          variants={reveal}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          <h2>Ship safer LLM flows in one pass</h2>
          <p>Start with quick integration, then enable preflight enforcement when you are ready.</p>
          <div className="marketing-hero-actions">
            <Link className="landing-link-button modal-primary" to="/login">
              Create account / Login
            </Link>
            <Link className="landing-link-button" to="/quickstart">
              Quickstart
            </Link>
          </div>
        </motion.section>

      </section>
    </PublicLayout>
  );
}
