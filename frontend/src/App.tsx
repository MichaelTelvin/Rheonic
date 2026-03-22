import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ApiError, fetchCurrentUser, logout, setUnauthorizedHandler, type AuthUser } from "./api/client";
import { AppToastHost } from "./components/AppToastHost";
import { CurrentProjectBar } from "./components/CurrentProjectBar";
import { FeedbackModal } from "./components/FeedbackModal";
import { Sidebar } from "./components/Sidebar";
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

  return (
    <div className="app-shell">
      <Sidebar userEmail={userEmail} onSignOut={onSignOut} onSendFeedback={() => setFeedbackModalOpen(true)} />
      <div className="app-main app-main-content">
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
      if (sessionResolved) {
        return () => {
          cancelled = true;
        };
      }

      const restorePublicSession = async (): Promise<void> => {
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
            emitFrontendLog({
              level: "error",
              event: "http_response",
              message: "Failed to restore browser session",
              metadata: { error },
            });
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

      void restorePublicSession();
      return () => {
        cancelled = true;
      };
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
