import { useCallback, useEffect, useState } from "react";

import { setUnauthorizedHandler, type AuthUser, type LoginResponse } from "./api/client";
import { frontendConfig } from "./config";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";

export function App(): JSX.Element {
  const [token, setToken] = useState<string | null>(() => window.localStorage.getItem(frontendConfig.authTokenStorageKey));
  const [user, setUser] = useState<AuthUser | null>(() => {
    const value = window.localStorage.getItem(frontendConfig.authUserStorageKey);
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
    window.localStorage.removeItem(frontendConfig.authTokenStorageKey);
    window.localStorage.removeItem(frontendConfig.authRefreshTokenStorageKey);
    window.localStorage.removeItem(frontendConfig.authUserStorageKey);
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
    window.localStorage.setItem(frontendConfig.authTokenStorageKey, auth.access_token);
    window.localStorage.setItem(frontendConfig.authRefreshTokenStorageKey, auth.refresh_token);
    window.localStorage.setItem(frontendConfig.authUserStorageKey, JSON.stringify(auth.user));
    setToken(auth.access_token);
    setUser(auth.user);
  };

  if (!token) {
    return <Login onAuthSuccess={onAuthSuccess} />;
  }

  return <Dashboard userEmail={user?.email ?? null} onSignOut={signOut} />;
}
