import { motion } from "framer-motion";
import { Activity, BellRing, Gauge, ShieldCheck, Workflow } from "lucide-react";
import { Link } from "react-router-dom";

import { PublicLayout } from "../components/PublicLayout";

const fadeUp = {
  hidden: { opacity: 0, y: 22 },
  visible: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.12,
      delayChildren: 0.12,
    },
  },
};

export function LandingPage(): JSX.Element {
  return (
    <PublicLayout
      navAuthHref="/login"
      navAuthLabel="Sign in"
      shellClassName="public-shell-marketing"
      showDocsLink={false}
    >
      <section className="landing-marketing">
        <motion.section
          className="landing-hero"
          initial="hidden"
          animate="visible"
          variants={stagger}
        >
          <motion.div className="landing-hero-left" variants={fadeUp}>
            <p className="landing-kicker">Runtime spend control for LLM apps</p>
            <h1>Guardrails and visibility for runaway token burn.</h1>
            <p className="landing-subline">
              Monitor provider traffic in realtime and enforce preflight decisions before cost spikes hit production.
            </p>
            <div className="landing-hero-cta">
              <Link className="landing-link-button modal-primary" to="/login">
                Sign in
              </Link>
              <Link className="landing-link-button" to="/quickstart">
                Quickstart
              </Link>
            </div>
          </motion.div>

          <motion.div className="landing-hero-right" variants={fadeUp}>
            <img
              className="landing-real-screenshot"
              src="/landing/dashboard-preview.svg?v=3"
              alt="LLMTokenBurnGuard dashboard"
            />
          </motion.div>
        </motion.section>

        <motion.section
          className="landing-chip-row"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          variants={stagger}
        >
          {[
            "Per-provider telemetry",
            "Realtime counters",
            "Incident timelines",
            "Preflight allow/warn/block",
          ].map((label) => (
            <motion.p key={label} variants={fadeUp}>
              {label}
            </motion.p>
          ))}
        </motion.section>

        <motion.section
          className="landing-two-col"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          variants={stagger}
        >
          <motion.article className="landing-panel" variants={fadeUp}>
            <h2>Why it exists</h2>
            <p>
              Teams discover LLM overspend too late. Token spikes and retry storms accumulate in minutes while apps keep
              calling providers.
            </p>
          </motion.article>
          <motion.article className="landing-panel" variants={fadeUp}>
            <h2>What you get</h2>
            <p>
              One control plane for counters, incidents, and protect actions across OpenAI, Anthropic, and Google
              providers.
            </p>
          </motion.article>
        </motion.section>

        <section className="landing-section">
          <h2>Core capabilities</h2>
          <motion.div
            className="landing-feature-grid"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-70px" }}
            variants={stagger}
          >
            <motion.article className="landing-feature-card" variants={fadeUp}>
              <span className="landing-feature-icon">
                <Gauge size={18} />
              </span>
              <h3>Realtime counters</h3>
              <p>Track requests and tokens in rolling 60-second windows per provider.</p>
            </motion.article>
            <motion.article className="landing-feature-card" variants={fadeUp}>
              <span className="landing-feature-icon">
                <Activity size={18} />
              </span>
              <h3>Incident detection</h3>
              <p>Detect near_cap, cap_breach, retry_storm, loop_suspect, and token_explosion patterns.</p>
            </motion.article>
            <motion.article className="landing-feature-card" variants={fadeUp}>
              <span className="landing-feature-icon">
                <ShieldCheck size={18} />
              </span>
              <h3>Protect decisions</h3>
              <p>Run preflight allow, warn, or block with cooldown before provider calls are sent.</p>
            </motion.article>
            <motion.article className="landing-feature-card" variants={fadeUp}>
              <span className="landing-feature-icon">
                <BellRing size={18} />
              </span>
              <h3>Webhook delivery</h3>
              <p>Dispatch protect-mode alerts with decision context and clamp recommendation details.</p>
            </motion.article>
          </motion.div>
        </section>

        <section className="landing-section">
          <h2>How it works</h2>
          <motion.div
            className="landing-steps"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-60px" }}
            variants={stagger}
          >
            <motion.article className="landing-step-card" variants={fadeUp}>
              <span>1</span>
              <h3>Install SDK</h3>
              <p>Configure backend URL and ingest key in your app runtime.</p>
            </motion.article>
            <motion.article className="landing-step-card" variants={fadeUp}>
              <span>2</span>
              <h3>Capture events</h3>
              <p>Send provider call telemetry for rolling counters and incidenting.</p>
            </motion.article>
            <motion.article className="landing-step-card" variants={fadeUp}>
              <span>3</span>
              <h3>Enable Protect</h3>
              <p>Turn on preflight decisions to warn or block before expensive calls execute.</p>
            </motion.article>
          </motion.div>
        </section>

        <section className="landing-section">
          <h2>Runtime schematic</h2>
          <motion.div
            className="landing-schematic-compact"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4 }}
          >
            <div className="landing-schematic-node">
              <Workflow size={16} />
              <p>SDK ingest events</p>
            </div>
            <span className="landing-schematic-arrow" />
            <div className="landing-schematic-node">
              <Gauge size={16} />
              <p>Counters + detectors</p>
            </div>
            <span className="landing-schematic-arrow" />
            <div className="landing-schematic-node">
              <BellRing size={16} />
              <p>Incidents + webhooks</p>
            </div>
            <span className="landing-schematic-arrow" />
            <div className="landing-schematic-node">
              <ShieldCheck size={16} />
              <p>Protect preflight</p>
            </div>
          </motion.div>
        </section>

        <motion.section
          className="landing-section"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          variants={stagger}
        >
          <h2>Observe vs Protect</h2>
          <div className="landing-compare">
            <motion.article className="landing-panel" variants={fadeUp}>
              <h3>Observe</h3>
              <p>Visibility mode. Logs incidents and counters, never blocks application traffic.</p>
            </motion.article>
            <motion.article className="landing-panel" variants={fadeUp}>
              <h3>Protect</h3>
              <p>Control mode. Executes preflight decisions, cooldown, and webhook dispatch for operations.</p>
            </motion.article>
          </div>
        </motion.section>

        <motion.section
          className="landing-final-cta"
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.38 }}
        >
          <div>
            <h2>Start with guardrails before scaling usage</h2>
            <p>Connect telemetry now, then enable protect enforcement when thresholds are calibrated.</p>
          </div>
          <div className="landing-hero-cta">
            <Link className="landing-link-button modal-primary" to="/login">
              Sign in
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
