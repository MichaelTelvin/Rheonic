import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { setUnauthorizedHandler, type AuthUser, type LoginResponse } from "./api/client";
import { getAuthItem, removeAuthItem, setAuthItem } from "./authStorage";
import { CurrentProjectBar } from "./components/CurrentProjectBar";
import { Sidebar } from "./components/Sidebar";
import { frontendConfig } from "./config";
import { ProjectProvider } from "./context/ProjectContext";
import { Architecture } from "./pages/Architecture";
import { Alerts } from "./pages/Alerts";
import { Dashboard } from "./pages/Dashboard";
import { Incidents } from "./pages/Incidents";
import { Keys } from "./pages/Keys";
import { Login } from "./pages/Login";
import { Projects } from "./pages/Projects";
import { Protect } from "./pages/Protect";

interface AuthenticatedAppLayoutProps {
  userEmail: string | null;
  onSignOut: () => void;
}

function AuthenticatedAppLayout({ userEmail, onSignOut }: AuthenticatedAppLayoutProps): JSX.Element {
  return (
    <div className="app-shell">
      <Sidebar userEmail={userEmail} onSignOut={onSignOut} />
      <div className="app-main app-main-content">
        <CurrentProjectBar />
        <div className="app-routes">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/keys" element={<Keys />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/protect" element={<Protect />} />
            <Route path="/docs" element={<Architecture />} />
            <Route path="/documentation" element={<Navigate to="/docs" replace />} />
            <Route path="/architecture" element={<Navigate to="/docs" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </div>
  );
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

  if (!token) {
    return <Login onAuthSuccess={onAuthSuccess} />;
  }

  return (
    <ProjectProvider>
      <AuthenticatedAppLayout userEmail={user?.email ?? null} onSignOut={signOut} />
    </ProjectProvider>
  );
}
