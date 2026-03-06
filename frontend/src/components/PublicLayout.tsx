import { useEffect, useState, type MouseEvent as ReactMouseEvent, type PropsWithChildren } from "react";
import { Link } from "react-router-dom";
import { fetchPublicConfig } from "../api/client";
import { getAuthItem, removeAuthItem } from "../authStorage";
import { frontendConfig } from "../config";
import { RheonicLogoMark } from "./RheonicLogoMark";

interface PublicLayoutProps extends PropsWithChildren {
  navAuthHref: string;
  navAuthLabel: string;
  shellClassName?: string;
  showQuickstartLink?: boolean;
  showHomeLink?: boolean;
  showDocsLink?: boolean;
  docsLinkLabel?: string;
  showBetaBadge?: boolean;
}

export function PublicLayout({
  navAuthHref,
  navAuthLabel,
  shellClassName,
  showQuickstartLink = true,
  showHomeLink = false,
  showDocsLink = true,
  docsLinkLabel = "Docs (dashboard)",
  showBetaBadge = false,
  children,
}: PublicLayoutProps): JSX.Element {
  const token = getAuthItem(frontendConfig.authTokenStorageKey);
  const isSignedIn = Boolean(token);
  const docsHref = token ? "/docs" : "/login";
  const authHref = isSignedIn ? "/" : navAuthHref;
  const authLabel = isSignedIn ? "Sign out" : navAuthLabel;
  const [scrolled, setScrolled] = useState(false);
  const [publicContactEmail, setPublicContactEmail] = useState<string>(frontendConfig.publicContactEmail || "feedback@example.com");
  const isV2Surface = shellClassName?.includes("public-shell-marketing") || shellClassName?.includes("quickstart-v2-shell");
  const isLandingFooter = shellClassName?.includes("public-shell-marketing");
  const isQuickstartFooter = shellClassName?.includes("quickstart-v2-shell");

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

  useEffect(() => {
    let cancelled = false;
    const loadPublicConfig = async (): Promise<void> => {
      try {
        const config = await fetchPublicConfig();
        if (!cancelled && (config.public_contact_email || "").trim()) {
          setPublicContactEmail(config.public_contact_email.trim());
        }
      } catch {
        if (!cancelled) {
          setPublicContactEmail(frontendConfig.publicContactEmail || "feedback@example.com");
        }
      }
    };
    void loadPublicConfig();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSignOut = (event: ReactMouseEvent<HTMLAnchorElement>): void => {
    if (!isSignedIn) {
      return;
    }
    event.preventDefault();
    removeAuthItem(frontendConfig.authTokenStorageKey);
    removeAuthItem(frontendConfig.authRefreshTokenStorageKey);
    removeAuthItem(frontendConfig.authUserStorageKey);
    window.location.assign("/");
  };

  return (
    <main className={`public-page${isV2Surface ? " public-page-v2" : ""}`}>
      <div className={`public-shell${shellClassName ? ` ${shellClassName}` : ""}`}>
        <header className={`public-nav public-nav-sticky${scrolled ? " is-scrolled" : ""}`}>
          <Link className="public-brand" to="/">
            <RheonicLogoMark className="brand-logo-icon" />
            <span className="public-brand-word">Rheonic</span>
            {showBetaBadge ? <span className="public-beta-badge">Beta</span> : null}
          </Link>
          <nav className="public-nav-links">
            {showHomeLink ? <Link to="/">Home</Link> : null}
            {showQuickstartLink ? <Link to="/quickstart">Quickstart</Link> : null}
            {showDocsLink ? <Link to={docsHref}>{docsLinkLabel}</Link> : null}
            <Link className="public-login-link" to={authHref} onClick={handleSignOut}>
              {authLabel}
            </Link>
          </nav>
        </header>

        {children}

        <footer className={`public-footer${isLandingFooter ? " public-footer-landing-legal" : ""}${isQuickstartFooter ? " public-footer-quickstart-legal" : ""}`}>
          {isLandingFooter ? (
            <>
              <div className="public-footer-links">
                <Link to="/quickstart">Quickstart</Link>
                <span aria-hidden="true" className="public-footer-dot">
                  ·
                </span>
                <Link to={authHref} onClick={handleSignOut}>
                  {isSignedIn ? "Sign out" : "Sign in"}
                </Link>
                <span aria-hidden="true" className="public-footer-dot">
                  ·
                </span>
                <Link to="/privacy">Privacy</Link>
                <span aria-hidden="true" className="public-footer-dot">
                  ·
                </span>
                <Link to="/terms">Terms</Link>
              </div>
              <p className="public-footer-contact">
                Questions or feedback:{" "}
                <span className="public-footer-contact-email">
                  {publicContactEmail}
                </span>
              </p>
              <p>© 2026 Rheonic</p>
            </>
          ) : isQuickstartFooter ? (
            <>
              <div className="public-footer-links">
                <Link to="/">Home</Link>
                <span aria-hidden="true" className="public-footer-dot">
                  ·
                </span>
                <Link to={docsHref}>{docsLinkLabel}</Link>
                <span aria-hidden="true" className="public-footer-dot">
                  ·
                </span>
                <Link to="/privacy">Privacy</Link>
                <span aria-hidden="true" className="public-footer-dot">
                  ·
                </span>
                <Link to="/terms">Terms</Link>
                <span aria-hidden="true" className="public-footer-dot">
                  ·
                </span>
                <Link to={authHref} onClick={handleSignOut}>
                  {isSignedIn ? "Sign out" : "Sign in"}
                </Link>
              </div>
              <p>© 2026 Rheonic</p>
            </>
          ) : (
            <>
              <div className="public-footer-links">
                {showHomeLink ? <Link to="/">Home</Link> : null}
                {showQuickstartLink ? <Link to="/quickstart">Quickstart</Link> : null}
                {showDocsLink ? <Link to={docsHref}>{docsLinkLabel}</Link> : null}
                <Link to={authHref} onClick={handleSignOut}>
                  {isSignedIn ? "Sign out" : "Sign in"}
                </Link>
              </div>
              <p>© {new Date().getFullYear()} Rheonic</p>
            </>
          )}
        </footer>
      </div>
    </main>
  );
}
