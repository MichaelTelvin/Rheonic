import { Card } from "../components/Card";

type DocItem = {
  title: string;
  description: string;
  href: string;
};

const docs: DocItem[] = [
  {
    title: "Onboarding",
    description: "Project scope, milestones, and current implementation status.",
    href: "/docs/viewer.html?doc=scope",
  },
  {
    title: "API Spec",
    description: "Backend contract, endpoint semantics, and data model details.",
    href: "/docs/viewer.html?doc=spec",
  },
  {
    title: "Protect Spec",
    description: "Protect-mode decisioning behavior and enforcement guarantees.",
    href: "/docs/viewer.html?doc=protect-mode-spec",
  },
  {
    title: "Thresholds Map",
    description: "Single reference for runtime thresholds, windows, and trigger conditions.",
    href: "/docs/viewer.html?doc=thresholds-map",
  },
  {
    title: "Product Design",
    description: "Product goals, UX framing, and design rationale snapshots.",
    href: "/docs/viewer.html?doc=product_design",
  },
];

export function Architecture(): JSX.Element {
  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Documentation</h1>
          <p className="page-subtitle">Architecture, onboarding, API reference, and operational guides</p>
        </section>

        <section className="docs-hub-grid">
          <Card className="doc-card card--content">
            <h2 className="section-title">Flow Charts</h2>
            <p className="subtle doc-card-description">
              Open architecture flows in the standalone chart viewer with clean, full-canvas rendering.
            </p>
            <div className="doc-card-actions">
              <a className="doc-cta action-btn" href="/documentation/viewer.html?tab=incident" target="_blank" rel="noreferrer">
                Open charts
              </a>
            </div>
          </Card>

          {docs.map((item) => (
            <Card className="doc-card card--form" key={item.title}>
              <h2 className="section-title">{item.title}</h2>
              <p className="subtle doc-card-description">{item.description}</p>
              <div className="doc-card-actions">
                <a className="doc-cta action-btn" href={item.href} target="_blank" rel="noreferrer">
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
