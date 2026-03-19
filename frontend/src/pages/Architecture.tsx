import { Card } from "../components/Card";

type DocItem = {
  title: string;
  description: string;
  href: string;
};

const docs: DocItem[] = [
  {
    title: "Overview",
    description: "What Rheonic does, core concepts, and where to start.",
    href: "/docs/viewer.html?doc=overview",
  },
  {
    title: "Quickstart",
    description: "Create a project, generate a key, send your first event, and verify setup.",
    href: "/docs/viewer.html?doc=quickstart",
  },
  {
    title: "Protect Mode",
    description: "Observe versus Protect, caps, fail modes, and rollout guidance.",
    href: "/docs/viewer.html?doc=protect-mode",
  },
  {
    title: "Incidents",
    description: "Incident types, lifecycle, filtering, and resolution workflow.",
    href: "/docs/viewer.html?doc=incidents",
  },
  {
    title: "Alerts",
    description: "Email and webhook delivery, test flow, and notification events.",
    href: "/docs/viewer.html?doc=alerts",
  },
  {
    title: "Roadmap",
    description: "Short view of planned product improvements and direction.",
    href: "/docs/viewer.html?doc=roadmap",
  },
  {
    title: "API Reference",
    description: "Customer-facing endpoint overview for auth, ingest, metrics, and protect.",
    href: "/docs/viewer.html?doc=api-reference",
  },
  {
    title: "Architecture",
    description: "High-level system flow and how telemetry, incidents, and protect fit together.",
    href: "/docs/viewer.html?doc=architecture",
  },
];

export function Architecture(): JSX.Element {
  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Documentation</h1>
          <p className="page-subtitle">Customer docs for setup, runtime protection, and operations</p>
        </section>

        <section className="docs-hub-grid">
          <Card className="doc-card card--content">
            <h2 className="section-title">Flow Charts</h2>
            <p className="subtle doc-card-description">
              Open architecture flows in the standalone chart viewer.
            </p>
            <div className="doc-card-actions">
              <a className="doc-cta action-btn" href="/docs/viewer.html?chart=incident" target="_blank" rel="noopener noreferrer">
                Open charts
              </a>
            </div>
          </Card>

          {docs.map((item) => (
            <Card className="doc-card card--form" key={item.title}>
              <h2 className="section-title">{item.title}</h2>
              <p className="subtle doc-card-description">{item.description}</p>
              <div className="doc-card-actions">
                <a className="doc-cta action-btn" href={item.href} target="_blank" rel="noopener noreferrer">
                  Open docs
                </a>
              </div>
            </Card>
          ))}
        </section>
      </div>
    </main>
  );
}
