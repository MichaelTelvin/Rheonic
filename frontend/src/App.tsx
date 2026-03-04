import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { setUnauthorizedHandler, type AuthUser, type LoginResponse } from "./api/client";
import { getAuthItem, removeAuthItem, setAuthItem } from "./authStorage";
import { CurrentProjectBar } from "./components/CurrentProjectBar";
import { Sidebar } from "./components/Sidebar";
import { AppToastHost } from "./components/AppToastHost";
import { frontendConfig } from "./config";
import { ProjectProvider } from "./context/ProjectContext";
import { Architecture } from "./pages/Architecture";
import { Alerts } from "./pages/Alerts";
import { Dashboard } from "./pages/Dashboard";
import { Incidents } from "./pages/Incidents";
import { LandingPage } from "./pages/LandingPage";
import { Keys } from "./pages/Keys";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { Projects } from "./pages/Projects";
import { Protect } from "./pages/Protect";
import { QuickstartPage } from "./pages/QuickstartPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { TermsPage } from "./pages/TermsPage";

interface AuthenticatedAppLayoutProps {
  userEmail: string | null;
  onSignOut: () => void;
}

function AuthenticatedAppLayout({ userEmail, onSignOut }: AuthenticatedAppLayoutProps): JSX.Element {
  useEffect(() => {
    const onPointerDown = (event: PointerEvent): void => {
      const target = event.target as HTMLElement | null;
      const select = target?.closest("select");
      if (!(select instanceof HTMLSelectElement)) {
        return;
      }
      if (!select.closest(".app-shell")) {
        return;
      }
      const rect = select.getBoundingClientRect();
      const minSpaceBelow = 260;
      const shortfall = minSpaceBelow - (window.innerHeight - rect.bottom);
      if (shortfall <= 0) {
        return;
      }
      const appMain = document.querySelector(".app-main") as HTMLElement | null;
      if (appMain && appMain.scrollHeight > appMain.clientHeight) {
        appMain.scrollBy({ top: shortfall + 12, behavior: "smooth" });
        return;
      }
      window.scrollBy({ top: shortfall + 12, behavior: "smooth" });
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
    };
  }, []);

  return (
    <div className="app-shell">
      <Sidebar userEmail={userEmail} onSignOut={onSignOut} />
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
    </div>
  );
}

interface RequireAuthProps {
  token: string | null;
  children: JSX.Element;
}

function RequireAuth({ token, children }: RequireAuthProps): JSX.Element {
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function App(): JSX.Element {
  const [token, setToken] = useState<string | null>(() => getAuthItem(frontendConfig.authTokenStorageKey));
  const [user, setUser] = useState<AuthUser | null>(() => {
    const value = getAuthItem(frontendConfig.authUserStorageKey);
    if (!value) {
      return null;
    }
    try {
      return JSON.parse(value) as AuthUser;
    } catch {
      return null;
    }
  });

  const signOut = useCallback((): void => {
    removeAuthItem(frontendConfig.authTokenStorageKey);
    removeAuthItem(frontendConfig.authRefreshTokenStorageKey);
    removeAuthItem(frontendConfig.authUserStorageKey);
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(signOut);
    return () => {
      setUnauthorizedHandler(null);
    };
  }, [signOut]);

  const onAuthSuccess = (auth: LoginResponse): void => {
    setAuthItem(frontendConfig.authTokenStorageKey, auth.access_token);
    setAuthItem(frontendConfig.authRefreshTokenStorageKey, auth.refresh_token);
    setAuthItem(frontendConfig.authUserStorageKey, JSON.stringify(auth.user));
    setToken(auth.access_token);
    setUser(auth.user);
  };

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/quickstart" element={<QuickstartPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/docs" element={<Navigate to="/app/docs" replace />} />
      <Route
        path="/login"
        element={token ? <Navigate to="/app" replace /> : <Login onAuthSuccess={onAuthSuccess} />}
      />
      <Route
        path="/signup"
        element={token ? <Navigate to="/app" replace /> : <Login onAuthSuccess={onAuthSuccess} />}
      />
      <Route
        path="/app/*"
        element={
          <RequireAuth token={token}>
            <ProjectProvider>
              <AuthenticatedAppLayout userEmail={user?.email ?? null} onSignOut={signOut} />
            </ProjectProvider>
          </RequireAuth>
        }
      />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
