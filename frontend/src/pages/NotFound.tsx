import { Link } from "react-router-dom";

import { Card } from "../components/Card";

interface NotFoundProps {
  inApp?: boolean;
}

export function NotFound({ inApp = false }: NotFoundProps): JSX.Element {
  if (inApp) {
    return (
      <main className="dashboard">
        <Card>
          <h1 className="page-title">Page not found</h1>
          <p className="page-subtitle">The page you&apos;re looking for doesn&apos;t exist.</p>
          <Link className="auth-button auth-button-primary" to="/app">
            Go to dashboard
          </Link>
        </Card>
      </main>
    );
  }

  return (
    <div className="auth-page">
      <Card className="auth-card">
        <h1 className="auth-title">Page not found</h1>
        <p className="auth-subtitle">The page you&apos;re looking for doesn&apos;t exist.</p>
        <div className="auth-actions">
          <Link className="auth-button auth-button-primary" to="/app">
            Go to dashboard
          </Link>
        </div>
      </Card>
    </div>
  );
}
