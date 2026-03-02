import { useEffect, useState, type PropsWithChildren } from "react";
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
  const [scrolled, setScrolled] = useState(false);
  const isV2Surface = shellClassName?.includes("public-shell-marketing") || shellClassName?.includes("quickstart-v2-shell");

  useEffect(() => {
    if (!isV2Surface) {
      return;
    }

    const onScroll = (): void => {
      setScrolled(window.scrollY > 8);
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [isV2Surface]);

  return (
    <main className={`public-page${isV2Surface ? " public-page-v2" : ""}`}>
      <div className={`public-shell${shellClassName ? ` ${shellClassName}` : ""}`}>
        <header className={`public-nav public-nav-sticky${scrolled ? " is-scrolled" : ""}`}>
          <p className="public-brand">Rheonic</p>
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
            <Link to="/login">Sign in</Link>
          </div>
          <p>© {new Date().getFullYear()} Rheonic</p>
        </footer>
      </div>
    </main>
  );
}
