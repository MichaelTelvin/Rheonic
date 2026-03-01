import { Link } from "react-router-dom";

export function Landing(): JSX.Element {
  return (
    <div className="auth-layout">
      <section className="auth-card" aria-label="Landing">
        <p className="auth-brand">LLMTokenBurnGuard</p>
        <h1 className="auth-title">Protect LLM spend and runtime behavior</h1>
        <p className="auth-subtitle">Monitor usage, detect anomalies, and enforce caps in one control center.</p>
        <ul className="auth-subtitle" style={{ margin: "0 0 0.25rem 1rem" }}>
          <li>Provider-scoped metrics and incidents</li>
          <li>Protect preflight allow, warn, and block decisions</li>
          <li>Webhook alerting and operational visibility</li>
        </ul>
        <div className="auth-actions" style={{ marginTop: "0.5rem" }}>
          <Link className="auth-button auth-button-primary" to="/app">
            Go to dashboard
          </Link>
          <Link className="auth-button auth-button-secondary" to="/login">
            Login
          </Link>
        </div>
      </section>
    </div>
  );
}
