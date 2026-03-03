import { Link } from "react-router-dom";

interface NotFoundProps {
  inApp?: boolean;
}

export function NotFound({ inApp = false }: NotFoundProps): JSX.Element {
  return (
    <main className={`notfound-page${inApp ? " notfound-page-in-app" : ""}`}>
      <div className="notfound-bg-code" aria-hidden="true">
        404
      </div>
      <div className="notfound-glow" aria-hidden="true" />
      <section className="notfound-content">
        <h1>Page not found</h1>
        <p>The page you&apos;re looking for doesn&apos;t exist or has been moved.</p>
        <div className="notfound-actions">
          <Link className="landing-link-button modal-primary" to="/app">
            Go to dashboard
          </Link>
        </div>
        <Link className="notfound-home-link" to="/">
          Go to home
        </Link>
      </section>
    </main>
  );
}
