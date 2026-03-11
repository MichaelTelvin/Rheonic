import { createContext, useContext } from "react";

import type { AuthUser } from "../api/client";

interface AuthContextValue {
  isAuthenticated: boolean;
  sessionResolved: boolean;
  user: AuthUser | null;
  signOut: () => void | Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuthContext(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuthContext must be used within AuthContext.Provider");
  }
  return context;
}
