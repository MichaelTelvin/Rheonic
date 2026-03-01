import type { PropsWithChildren } from "react";
import { Link } from "react-router-dom";
import { getAuthItem } from "../authStorage";
import { frontendConfig } from "../config";

interface PublicLayoutProps extends PropsWithChildren {
  navAuthHref: string;
  navAuthLabel: string;
  shellClassName?: string;
  showQuickstartLink?: boolean;
  showHomeLink?: boolean;
  showDocsLink?: boolean;
}

export function PublicLayout({
  navAuthHref,
  navAuthLabel,
  shellClassName,
  showQuickstartLink = true,
  showHomeLink = false,
  showDocsLink = true,
  children,
}: PublicLayoutProps): JSX.Element {
  const token = getAuthItem(frontendConfig.authTokenStorageKey);
  const docsHref = token ? "/docs" : "/login";

  return (
    <main className="public-page">
      <div className={`public-shell${shellClassName ? ` ${shellClassName}` : ""}`}>
        <header className="public-nav public-nav-sticky">
          <p className="public-brand">LLMTokenBurnGuard</p>
          <nav className="public-nav-links">
            {showHomeLink ? <Link to="/">Home</Link> : null}
            {showQuickstartLink ? <Link to="/quickstart">Quickstart</Link> : null}
            {showDocsLink ? <Link to={docsHref}>Docs (dashboard)</Link> : null}
            <Link className="public-login-link" to={navAuthHref}>
              {navAuthLabel}
            </Link>
          </nav>
        </header>

        {children}

        <footer className="public-footer">
          <div className="public-footer-links">
            {showHomeLink ? <Link to="/">Home</Link> : null}
            {showQuickstartLink ? <Link to="/quickstart">Quickstart</Link> : null}
            {showDocsLink ? <Link to={docsHref}>Docs (dashboard)</Link> : null}
            <Link to="/login">Login</Link>
          </div>
          <p>© {new Date().getFullYear()} LLMTokenBurnGuard</p>
        </footer>
      </div>
    </main>
  );
}
