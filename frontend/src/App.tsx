import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ApiError, fetchApiVersion, fetchCurrentUser, logout, setUnauthorizedHandler, type AuthUser } from "./api/client";
import { AppToastHost } from "./components/AppToastHost";
import { CurrentProjectBar } from "./components/CurrentProjectBar";
import { FeedbackModal } from "./components/FeedbackModal";
import { RheonicLogoMark } from "./components/RheonicLogoMark";
import { Sidebar } from "./components/Sidebar";
import { frontendConfig } from "./config";
import { AuthContext } from "./context/AuthContext";
import { ProjectProvider } from "./context/ProjectContext";
import { emitFrontendLog } from "./lib/logger";
import { Alerts } from "./pages/Alerts";
import { Architecture } from "./pages/Architecture";
import { Dashboard } from "./pages/Dashboard";
import { DpaPage } from "./pages/DpaPage";
import { Incidents } from "./pages/Incidents";
import { Keys } from "./pages/Keys";
import { LandingPage } from "./pages/LandingPage";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { PrivacyPage } from "./pages/PrivacyPage";
import { Projects } from "./pages/Projects";
import { Protect } from "./pages/Protect";
import { QuickstartPage } from "./pages/QuickstartPage";
import { TermsPage } from "./pages/TermsPage";

const authUserCacheStorageKey = "auth_user_cache";
const legacyAuthStorageKeys = ["rheonic_token", "rheonic_refresh_token", "rheonic_user"];
const sensitiveSessionCachePrefixes = ["rheonic:alerts:", "rheonic:dashboard:"];

function clearLegacyAuthStorage(): void {
  try {
    for (const key of legacyAuthStorageKeys) {
      window.localStorage.removeItem(key);
      window.sessionStorage.removeItem(key);
    }
    for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
      const key = window.localStorage.key(index);
      if (key?.startsWith("rheonic:setupBannerDismissed:")) {
        window.localStorage.removeItem(key);
      }
    }
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = window.sessionStorage.key(index);
      if (key?.startsWith("rheonic:setupBannerDismissed:")) {
        window.sessionStorage.removeItem(key);
      }
      if (key && sensitiveSessionCachePrefixes.some((prefix) => key.startsWith(prefix))) {
        window.sessionStorage.removeItem(key);
      }
    }
  } catch {
    // Ignore storage cleanup failures.
  }
}

function readCachedAuthUser(): AuthUser | null {
  try {
    const raw = window.sessionStorage.getItem(authUserCacheStorageKey);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as AuthUser;
    if (
      typeof parsed?.id !== "string"
      || typeof parsed?.email !== "string"
      || typeof parsed?.created_at !== "string"
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeCachedAuthUser(user: AuthUser | null): void {
  try {
    if (user) {
      window.sessionStorage.setItem(authUserCacheStorageKey, JSON.stringify(user));
    } else {
      window.sessionStorage.removeItem(authUserCacheStorageKey);
    }
  } catch {
    // Ignore storage write failures and keep runtime auth authoritative.
  }
}

interface AuthenticatedAppLayoutProps {
  userEmail: string | null;
  onSignOut: () => void | Promise<void>;
}

function AuthenticatedAppLayout({ userEmail, onSignOut }: AuthenticatedAppLayoutProps): JSX.Element {
  const [feedbackModalOpen, setFeedbackModalOpen] = useState<boolean>(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState<boolean>(false);
  const [appVersion, setAppVersion] = useState<string>(frontendConfig.appVersion);
  const location = useLocation();

  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    let cancelled = false;
    const loadVersion = async (): Promise<void> => {
      try {
        const payload = await fetchApiVersion();
        const nextVersion = payload.version.trim();
        if (!cancelled && nextVersion) {
          setAppVersion(nextVersion);
        }
      } catch {
        // Keep the build-time fallback when the API version endpoint is unavailable.
      }
    };
    void loadVersion();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="app-shell">
      <Sidebar
        userEmail={userEmail}
        onSignOut={onSignOut}
        onSendFeedback={() => setFeedbackModalOpen(true)}
        isMobileOpen={mobileSidebarOpen}
        onRequestClose={() => setMobileSidebarOpen(false)}
      />
      {mobileSidebarOpen ? <button type="button" className="mobile-nav-backdrop" aria-label="Close navigation" onClick={() => setMobileSidebarOpen(false)} /> : null}
      <div className="app-main app-main-content">
        <div className="mobile-app-bar">
          <Link className="mobile-app-brand" to="/" aria-label="Go to Rheonic site">
            <RheonicLogoMark className="brand-logo-icon" />
            <span className="dashboard-brand-word">Rheonic</span>
            <span className="dashboard-beta-badge">BETA</span>
          </Link>
          <button
            type="button"
            className="mobile-nav-toggle"
            aria-label={mobileSidebarOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileSidebarOpen}
            onClick={() => setMobileSidebarOpen((open) => !open)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
        <CurrentProjectBar />
        <div className="app-routes">
          <Routes>
            <Route index element={<Dashboard />} />
            <Route path="incidents" element={<Incidents />} />
            <Route path="projects" element={<Projects />} />
            <Route path="keys" element={<Keys />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="settings" element={<Protect />} />
            <Route path="docs" element={<Architecture />} />
            <Route path="*" element={<NotFound inApp />} />
          </Routes>
        </div>
      </div>
      {appVersion ? <div className="app-version-badge">v{appVersion}</div> : null}
      <AppToastHost />
      <FeedbackModal open={feedbackModalOpen} onClose={() => setFeedbackModalOpen(false)} />
    </div>
  );
}

interface RequireAuthProps {
  isAuthenticated: boolean;
  sessionResolved: boolean;
  children: JSX.Element;
}

function ScrollToTop(): null {
  const location = useLocation();

  useEffect(() => {
    const appMain = document.querySelector(".app-main");
    if (appMain instanceof HTMLElement && typeof appMain.scrollTo === "function") {
      appMain.scrollTo({ top: 0, left: 0, behavior: "auto" });
    }
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return null;
}

function RequireAuth({ isAuthenticated, sessionResolved, children }: RequireAuthProps): JSX.Element {
  if (!sessionResolved) {
    return <main className="auth-page" aria-busy="true" />;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function App(): JSX.Element {
  const location = useLocation();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [sessionResolved, setSessionResolved] = useState<boolean>(false);

  useEffect(() => {
    clearLegacyAuthStorage();
  }, []);

  const clearSession = useCallback((): void => {
    writeCachedAuthUser(null);
    setUser(null);
    setSessionResolved(true);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(clearSession);
    return () => {
      setUnauthorizedHandler(null);
    };
  }, [clearSession]);

  useEffect(() => {
    let cancelled = false;
    const publicRoutes = new Set(["/", "/quickstart", "/privacy", "/terms", "/dpa", "/login", "/signup"]);
    const authEntryRoutes = new Set(["/login", "/signup"]);

    if (publicRoutes.has(location.pathname)) {
      if (user) {
        setSessionResolved(true);
        return () => {
          cancelled = true;
        };
      }
      const cachedUser = readCachedAuthUser();
      if (cachedUser) {
        setUser(cachedUser);
        setSessionResolved(true);
        return () => {
          cancelled = true;
        };
      }
      if (authEntryRoutes.has(location.pathname) || publicRoutes.has(location.pathname)) {
        setSessionResolved(true);
        return () => {
          cancelled = true;
        };
      }
    }

    const restoreSession = async (): Promise<void> => {
      try {
        const currentUser = await fetchCurrentUser();
        if (!cancelled) {
          writeCachedAuthUser(currentUser);
          setUser(currentUser);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (!(error instanceof ApiError) || error.status !== 401) {
          const cachedUser = readCachedAuthUser();
          emitFrontendLog({
            level: "error",
            event: "http_response",
            message: "Failed to restore browser session",
            metadata: { error },
          });
          setUser(cachedUser);
        } else {
          writeCachedAuthUser(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) {
          setSessionResolved(true);
        }
      }
    };

    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  const signOut = useCallback(async (): Promise<void> => {
    try {
      await logout();
    } catch (error) {
      emitFrontendLog({
        level: "error",
        event: "http_response",
        message: "Logout request failed",
        metadata: { error },
      });
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const onAuthSuccess = (nextUser: AuthUser): void => {
    writeCachedAuthUser(nextUser);
    setUser(nextUser);
    setSessionResolved(true);
  };

  const authContextValue = {
    isAuthenticated: Boolean(user),
    sessionResolved,
    user,
    signOut,
  };

  return (
    <AuthContext.Provider value={authContextValue}>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/quickstart" element={<QuickstartPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/dpa" element={<DpaPage />} />
        <Route path="/docs" element={<Navigate to="/app/docs" replace />} />
        <Route
          path="/login"
          element={
            !sessionResolved ? <main className="auth-page" aria-busy="true" /> : (
              user ? <Navigate to="/app" replace /> : <Login onAuthSuccess={onAuthSuccess} />
            )
          }
        />
        <Route
          path="/signup"
          element={
            !sessionResolved ? <main className="auth-page" aria-busy="true" /> : (
              user ? <Navigate to="/app" replace /> : <Login onAuthSuccess={onAuthSuccess} />
            )
          }
        />
        <Route
          path="/app/*"
          element={
            <RequireAuth isAuthenticated={Boolean(user)} sessionResolved={sessionResolved}>
              <ProjectProvider>
                <AuthenticatedAppLayout userEmail={user?.email ?? null} onSignOut={signOut} />
              </ProjectProvider>
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AuthContext.Provider>
  );
}
