import { useCallback, useEffect, useState } from "react";

import { setUnauthorizedHandler, type AuthUser, type LoginResponse } from "./api/client";
import { getAuthItem, removeAuthItem, setAuthItem } from "./authStorage";
import { frontendConfig } from "./config";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";

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

  return <Dashboard userEmail={user?.email ?? null} onSignOut={signOut} />;
}
